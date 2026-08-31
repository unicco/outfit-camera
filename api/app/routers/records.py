"""コーディネート記録エンドポイント."""

import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..api_shared import PhotoRepository
from ..schemas.api_v2 import RecordResponse
from ..database import get_db
from ..schemas.base import BaseModel
from ..settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["records"])


class OutfitRecord(BaseModel):
    """コーディネート記録モデル."""

    id: str
    date: str
    photo_id: Optional[str] = None
    clothing_items: List[str] = []
    notes: Optional[str] = None
    created_at: datetime
    person_detected: bool = False


@router.get("/records", response_model=List[OutfitRecord])
async def get_outfit_records(
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> List[OutfitRecord]:
    """コーディネート記録を取得.

    Args:
        limit: 取得する記録数（最大100）
        offset: スキップする記録数
        db: データベースセッション（有効時のみ）

    Returns:
        コーディネート記録のリスト

    """
    logger.info(f"Fetching outfit records: limit={limit}, offset={offset}")

    if not get_settings().db_enabled:
        logger.error("Database access requested while database is disabled")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable. Please check database connection.",
        )

    try:
        from ..models import OutfitRecord as DBOutfitRecord

        records = (
            db.query(DBOutfitRecord)
            .order_by(DBOutfitRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        def build_outfit_record(record: DBOutfitRecord) -> OutfitRecord:
            # date フィールドが存在しないモデルもあるため、recorded_at をフォールバックに使用
            date_value = getattr(record, "date", None) or getattr(
                record, "recorded_at", None
            )
            if isinstance(date_value, datetime):
                date_str = date_value.isoformat()
            else:
                date_str = date_value or ""

            return OutfitRecord(
                id=str(record.id),
                date=date_str,
                photo_id=getattr(record, "photo_id", None),
                clothing_items=getattr(record, "clothing_items", []) or [],
                notes=getattr(record, "notes", None),
                created_at=getattr(record, "created_at", datetime.now()),
                person_detected=getattr(record, "person_detected", False),
            )

        return [build_outfit_record(record) for record in records]

    except Exception as exc:
        logger.exception("Failed to fetch records from database: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable. Please check database connection.",
        ) from exc


@router.delete("/records/no-person", response_model=None)
async def delete_no_person_records(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Delete all records where no person was detected."""
    try:
        repo = PhotoRepository(db)
        deleted_count = repo.delete_no_person_photos()

        return {
            "success": True,
            "message": f"{deleted_count}件の「人物なし」記録を削除しました",
            "deleted_count": deleted_count,
        }
    except Exception as e:
        logger.error(f"Failed to delete no-person records: {e}")
        raise HTTPException(status_code=500, detail="削除に失敗しました") from e


@router.get("/dates", response_model=None)
async def get_available_dates(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Get list of dates with detailed information for calendar."""
    try:
        repo = PhotoRepository(db)
        # Get daily summary for all days
        summary = repo.get_daily_summary(days=365)  # Get last year

        # Return detailed information for each date
        dates_info = []
        for s in summary:
            if s["total_count"] > 0:  # Only include dates with photos
                dates_info.append(
                    {
                        "date": s["date"],
                        "captured": True,
                        "total_count": s["total_count"],
                        "person_count": s["person_count"],
                        "last_capture": s["last_capture"],
                    }
                )

        return sorted(dates_info, key=lambda x: x["date"], reverse=True)
    except Exception as e:
        logger.error(f"Failed to get available dates: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get available dates"
        ) from e


@router.get("/records/by-clothing/{clothing_item}", response_model=None)
async def get_records_by_clothing(
    clothing_item: str, db: Session = Depends(get_db)
) -> list[RecordResponse]:
    """Get records filtered by specific clothing item."""
    try:
        repo = PhotoRepository(db)
        # Get all photos and filter by clothing item
        photos = repo.get_recent(limit=1000)  # Get many photos

        # Filter photos that contain the clothing item
        filtered_photos = [
            photo
            for photo in photos
            if photo.clothing_items and clothing_item in photo.clothing_items
        ]

        # Convert to legacy format
        return [
            RecordResponse(
                id=str(photo.id),
                date=photo.captured_at.date().isoformat(),
                timestamp=photo.captured_at.isoformat(),
                photo_id=str(photo.id),
                person_detected=bool(photo.person_detected),
                clothing_items=(
                    list(photo.clothing_items) if photo.clothing_items else []
                ),
                notes=None,
            )
            for photo in filtered_photos
        ]
    except Exception as e:
        logger.error(f"Failed to get records by clothing: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get records by clothing"
        ) from e
