"""Daily capture status / dashboard endpoints .

Extracted verbatim from the ``api.py`` monolith (now removed). Shared helpers
(``get_db``/``DB_AVAILABLE``/``DATABASE_MODE``/``PhotoRepository``/emergency
responses) live in their permanent home ``..api_shared`` .
"""

import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api_shared import (
    DATABASE_MODE,
    DB_AVAILABLE,
    PhotoRepository,
    get_db,
    get_emergency_stats_response,
)
from ..services.photo_utils import get_effective_date

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["status"])


@router.get("/daily-status", response_model=None)
async def get_daily_status(
    db: Session | None = Depends(get_db) if DB_AVAILABLE else None,
) -> dict[str, Any]:
    """Get daily capture status."""
    today = date.today()

    if not DB_AVAILABLE or db is None:
        logger.error("Database not available for daily-status endpoint")
        raise HTTPException(
            status_code=503,
            detail="Database service is unavailable. Please check database connection.",
        )

    # Database-based implementation
    try:
        repo = PhotoRepository(db)

        # Get today's photos
        today_photos = repo.get_by_date(today)

        # Get daily summary for last 7 days
        summary = repo.get_daily_summary(days=7)

        # Build history dict
        history = {}
        for day_summary in summary:
            # Handle last_capture formatting
            last_capture_formatted = None
            if day_summary["last_capture"]:
                if isinstance(day_summary["last_capture"], str):
                    last_capture_formatted = day_summary["last_capture"]
                else:
                    try:
                        last_capture_formatted = day_summary["last_capture"].isoformat()
                    except AttributeError:
                        last_capture_formatted = str(day_summary["last_capture"])

            history[day_summary["date"]] = {
                "captured": day_summary["captured"],
                "count": day_summary["total_count"],
                "last_capture": last_capture_formatted,
            }

        # Ensure today is in history
        if today.isoformat() not in history:
            history[today.isoformat()] = {
                "captured": False,
                "count": 0,
                "last_capture": None,
            }

        logger.info(
            f"Database mode: Found {len(today_photos)} photos for today, {len(summary)} days in history"
        )

        # Calculate last_capture safely with explicit type checking
        last_capture_db: datetime | None = None
        if today_photos:
            try:
                last_capture_times: list[datetime] = []
                for p in today_photos:
                    if hasattr(p, "captured_at") and p.captured_at:
                        # p.captured_at should be datetime from SQLAlchemy model
                        # Use type ignore to handle mypy's Column type confusion
                        captured_at: datetime = p.captured_at  # type: ignore[assignment]
                        last_capture_times.append(captured_at)
                if last_capture_times:
                    last_capture_db = max(last_capture_times)
            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"Error processing capture times: {e}")
                last_capture_db = None

        return {
            "status": {
                "date": today.isoformat(),
                "captured_today": len(today_photos) > 0,
                "capture_count": len(today_photos),
                "last_capture": (
                    last_capture_db.isoformat() if last_capture_db else None
                ),
                "storage_stats": repo.get_storage_stats(),
            },
            "history": history,
            "version": "v2",
        }

    except Exception as e:
        import traceback

        error_traceback = traceback.format_exc()
        logger.error(
            f"Database operation failed in daily-status: {str(e)}\nTraceback: {error_traceback}"
        )
        raise HTTPException(
            status_code=500, detail="Failed to retrieve daily status"
        ) from e


@router.get("/stats", response_model=None)
async def get_system_stats(
    db: Session | None = Depends(get_db) if DB_AVAILABLE else None,
) -> dict[str, Any]:
    """Get system statistics."""
    # Handle DATABASE_MODE settings
    if DATABASE_MODE == "required":
        if not DB_AVAILABLE or db is None:
            raise HTTPException(
                status_code=503, detail="Database required but unavailable"
            )
    elif DATABASE_MODE == "fileonly":
        return get_emergency_stats_response()
    elif not DB_AVAILABLE or db is None:
        return get_emergency_stats_response()

    repo = PhotoRepository(db)
    storage_stats = repo.get_storage_stats()

    return {
        "photos": storage_stats,
        "database": {"healthy": True, "type": "postgresql"},
    }


@router.post("/daily-reset", response_model=None)
async def reset_daily_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Reset today's capture status (for testing/manual override)."""
    try:
        # For database-backed implementation, we just return success
        # The daily status is calculated dynamically based on photos
        return {"success": True, "message": "Today's capture status has been reset"}
    except Exception as e:
        logger.error(f"Failed to reset daily status: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to reset daily status"
        ) from e


@router.get("/capture-required", response_model=None)
async def is_capture_required(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Check if capture is required today."""
    try:
        repo = PhotoRepository(db)
        today = get_effective_date()  # 午前7時基準の日付
        today_photos = repo.get_by_date(today)

        # 🔥 修正: 人物検出ではなく、今日撮影された写真が1枚以上あるかで判定
        photos_taken_today = len(today_photos) > 0

        return {
            "capture_required": not photos_taken_today,
            "already_captured": photos_taken_today,
            "capture_count_today": len(today_photos),
            "message": "撮影済" if photos_taken_today else "今日の撮影が必要です",
            "today_date": str(today),  # デバッグ用：有効日付を表示
            "photos_detail": [  # デバッグ用：今日の写真詳細
                {
                    "id": str(p.id),
                    "captured_at": p.captured_at.isoformat() if p.captured_at else None,
                    "filename": p.filename,
                }
                for p in today_photos
            ],
        }
    except Exception as e:
        logger.error(f"Failed to check capture requirement: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to check capture requirement"
        ) from e
