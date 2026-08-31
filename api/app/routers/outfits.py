"""Outfit Records API router
Issue #200 implementation.
"""

from typing import Any, Dict, List, Optional, Union, cast
from uuid import UUID
from datetime import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import func

from ..database import get_db
from ..external_rental_models import ExternalRentalItem
from ..security import require_write_access
from ..models import OutfitExternalRentalItem, OutfitItem, OutfitRecord
from ..wardrobe_models import ClothingItem
from ..schemas.base import BaseModel
from ..co_occurrence_service import CoOccurrenceService
from ..utils.timezone_utils import TimezoneUtils, jst_now

router = APIRouter(prefix="/api/v2/outfits", tags=["outfits"])
logger = logging.getLogger(__name__)


def _decrement_clothing_usage_count(db: Session, clothing_item_id: str) -> None:
    """衣類アイテムの着用回数をデクリメント.

    Args:
        db: データベースセッション
        clothing_item_id: 衣類アイテムID

    """
    clothing_item = (
        db.query(ClothingItem).filter(ClothingItem.id == clothing_item_id).first()
    )

    if clothing_item:
        current_count = clothing_item.usage_count or 0
        clothing_item.usage_count = max(0, current_count - 1)
        logger.debug(
            f"Decremented usage count for item {clothing_item_id}: "
            f"usage_count={clothing_item.usage_count}"
        )


def _increment_clothing_usage_count(
    db: Session, clothing_item_id: str, recorded_date: datetime
) -> None:
    """衣類アイテムの着用回数をインクリメント.

    Args:
        db: データベースセッション
        clothing_item_id: 衣類アイテムID
        recorded_date: 記録日時

    """
    clothing_item = (
        db.query(ClothingItem).filter(ClothingItem.id == clothing_item_id).first()
    )

    if clothing_item and clothing_item.status != "DISPOSED":
        current_count = clothing_item.usage_count or 0
        clothing_item.usage_count = current_count + 1

        # 最終着用日を更新（より新しい日付を保持）
        new_used_date = recorded_date.date()
        if (
            clothing_item.last_used_date is None
            or new_used_date > clothing_item.last_used_date
        ):
            clothing_item.last_used_date = new_used_date

        logger.debug(
            f"Updated usage count for item {clothing_item_id}: "
            f"usage_count={clothing_item.usage_count}, "
            f"last_used_date={clothing_item.last_used_date}"
        )


# Pydantic models for request/response
class OutfitRecordCreate(BaseModel):
    photo_id: Optional[str] = None
    clothing_item_ids: List[str]
    notes: Optional[str] = None
    recorded_at: Optional[datetime] = None  # 手動日付指定を可能にする
    external_rental_item_ids: List[str] = Field(default_factory=list)


class OutfitItemResponse(BaseModel):
    id: str
    outfit_record_id: str
    clothing_item_id: str
    detection_confidence: Optional[float]
    manual_added: bool
    position_x: Optional[int]
    position_y: Optional[int]
    created_at: str
    clothing_item: dict  # Simplified clothing item data


class ExternalRentalItemBasicResponse(BaseModel):
    id: str
    source: Optional[str] = None
    name: str
    brand: Optional[str] = None
    size: Optional[str] = None
    management_number: Optional[str] = None
    return_due_date: Optional[str] = None
    status: Optional[str] = None
    wear_count: Optional[int] = None
    last_worn_at: Optional[str] = None
    image_url: Optional[str] = None


class OutfitExternalRentalItemResponse(BaseModel):
    id: str
    external_rental_item_id: str
    created_at: str
    external_rental_item: ExternalRentalItemBasicResponse


class OutfitRecordResponse(BaseModel):
    id: str
    photo_id: Optional[str]
    recorded_at: str
    confidence_score: Optional[float]
    manual_selection: bool
    notes: Optional[str]
    created_at: str
    updated_at: str
    outfit_items: List[OutfitItemResponse]
    external_rental_items: List[OutfitExternalRentalItemResponse] = Field(
        default_factory=list
    )


class SimpleClothingItemResponse(BaseModel):
    id: str
    name: str
    category: str
    brand: Optional[str]
    image_urls: Optional[Dict[str, Any]]


class SimpleOutfitItemResponse(BaseModel):
    id: str
    clothing_item: SimpleClothingItemResponse


class SimpleOutfitRecordResponse(BaseModel):
    id: Optional[str]
    photo_id: Optional[str]
    clothing_items: List[SimpleOutfitItemResponse]
    external_rental_item_ids: List[str] = Field(default_factory=list)


class BatchOutfitRequest(BaseModel):
    photo_ids: List[str]


class BatchOutfitResponse(BaseModel):
    results: Dict[str, SimpleOutfitRecordResponse]


class DateRangeClothingItemResponse(BaseModel):
    """Clothing item response for date range endpoint."""

    id: str
    name: str
    category: str
    brand: Optional[str]
    image_urls: Optional[Union[Dict[str, Any], List[str]]]


class OutfitRecordDateRangeResponse(BaseModel):
    """Outfit record response for date range endpoint."""

    date: str
    outfit_record_id: str  # This will be converted to outfitRecordId in JSON
    photo_id: Optional[str]  # This will be converted to photoId in JSON
    clothing_items: List[
        DateRangeClothingItemResponse
    ]  # This will be converted to clothingItems in JSON
    external_rental_item_ids: List[str] = Field(default_factory=list)
    external_rental_items: List[ExternalRentalItemBasicResponse] = Field(
        default_factory=list
    )


def _parse_and_validate_recorded_at(
    recorded_at: Union[str, datetime], logger: logging.Logger
) -> datetime:
    """記録日時の解析とバリデーション."""
    if isinstance(recorded_at, str):
        try:
            if len(recorded_at) == 10:  # YYYY-MM-DD format
                parsed_date = TimezoneUtils.parse_date_as_jst_noon(recorded_at)
            else:
                # ISO 8601 形式の日付文字列をパース
                from dateutil.parser import parse as parse_date

                parsed_date = parse_date(recorded_at)
                parsed_date = TimezoneUtils.to_jst(parsed_date)
            return parsed_date
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="日付フォーマットが無効です。YYYY-MM-DD形式を使用してください。",
            )
    else:
        # datetimeオブジェクトの場合はJSTに変換
        return TimezoneUtils.to_jst(recorded_at)


@router.post("/record", response_model=dict)
async def create_outfit_record(
    record_data: OutfitRecordCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_write_access),
) -> dict:
    """着用記録を作成または更新."""
    try:
        import logging

        logger = logging.getLogger(__name__)
        # 全リクエストボディ（着用内容・日時などの PII）はレベルを debug に落とす
        logger.debug(f"Received outfit record data: {record_data}")
        logger.debug(
            f"recorded_at type: {type(record_data.recorded_at)}, value: {record_data.recorded_at}"
        )

        photo_id = record_data.photo_id.strip() if record_data.photo_id else None
        record_data.photo_id = photo_id

        # 日付バリデーション: 未来の日付は許可しない
        if record_data.recorded_at:
            record_data.recorded_at = _parse_and_validate_recorded_at(
                record_data.recorded_at, logger
            )

            # 未来の日付チェック（JST基準）
            now_jst = TimezoneUtils.now_jst()
            # 日付レベルで比較（時刻は無視）
            record_date = record_data.recorded_at.date()
            today_jst = now_jst.date()

            if record_date > today_jst:
                raise HTTPException(
                    status_code=400, detail="未来の日付はコーディネート記録できません。"
                )

        # Normalize external rental IDs (deduplicate + UUID validation)
        normalized_rental_ids: List[str] = []
        for rental_id in record_data.external_rental_item_ids or []:
            if rental_id is None:
                continue
            rental_id_str = rental_id.strip()
            if not rental_id_str:
                continue
            try:
                UUID(rental_id_str)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"無効なレンタルアイテムIDフォーマット: {rental_id}",
                )
            if rental_id_str not in normalized_rental_ids:
                normalized_rental_ids.append(rental_id_str)

        external_rental_item_ids = normalized_rental_ids
        record_data.external_rental_item_ids = external_rental_item_ids
        # Check if outfit record already exists for this photo
        # For photo-less records, also check the date to avoid overwriting different days
        if photo_id:
            # Photo-based record: check by photo_id only
            existing_record = (
                db.query(OutfitRecord).filter(OutfitRecord.photo_id == photo_id).first()
            )
        else:
            # Photo-less record: check by photo_id AND date to avoid cross-date conflicts
            if record_data.recorded_at:
                # Get date range for the target date to compare
                target_date_str = TimezoneUtils.extract_date_part(
                    record_data.recorded_at
                )
                start_datetime, end_datetime = TimezoneUtils.get_jst_date_range(
                    target_date_str
                )

                existing_record = (
                    db.query(OutfitRecord)
                    .filter(OutfitRecord.photo_id == photo_id)
                    .filter(OutfitRecord.recorded_at >= start_datetime)
                    .filter(OutfitRecord.recorded_at <= end_datetime)
                    .first()
                )
            else:
                # No date provided, fall back to photo_id only
                existing_record = (
                    db.query(OutfitRecord)
                    .filter(OutfitRecord.photo_id == photo_id)
                    .first()
                )

        if existing_record:
            # Update existing record
            existing_record.notes = record_data.notes
            existing_record.updated_at = func.now()
            # Update recorded_at if provided
            if record_data.recorded_at:
                existing_record.recorded_at = record_data.recorded_at
            outfit_record = existing_record

            # Before deleting, decrement usage count for existing items (Issue #921)
            existing_outfit_items = (
                db.query(OutfitItem)
                .filter(OutfitItem.outfit_record_id == existing_record.id)
                .all()
            )

            for existing_item in existing_outfit_items:
                _decrement_clothing_usage_count(db, existing_item.clothing_item_id)

            # Delete existing outfit items
            db.query(OutfitItem).filter(
                OutfitItem.outfit_record_id == existing_record.id
            ).delete()

            # Remove existing external rental links and roll back wear counts
            existing_rental_links: List[OutfitExternalRentalItem] = (
                db.query(OutfitExternalRentalItem)
                .filter(OutfitExternalRentalItem.outfit_record_id == existing_record.id)
                .all()
            )
            if existing_rental_links:
                rental_ids_to_update = [
                    link.external_rental_item_id for link in existing_rental_links
                ]
                rental_items = (
                    db.query(ExternalRentalItem)
                    .filter(ExternalRentalItem.id.in_(rental_ids_to_update))
                    .all()
                )
                rentals_by_id = {item.id: item for item in rental_items}
                for link in existing_rental_links:
                    rental_item = rentals_by_id.get(link.external_rental_item_id)
                    if rental_item and rental_item.wear_count:
                        rental_item.wear_count = max(0, rental_item.wear_count - 1)
                        if rental_item.wear_count == 0:
                            rental_item.last_worn_at = None

                db.query(OutfitExternalRentalItem).filter(
                    OutfitExternalRentalItem.outfit_record_id == existing_record.id
                ).delete()

            logger.info(f"既存レコードを更新: {existing_record.id}")
        else:
            # Create new outfit record
            outfit_record = OutfitRecord(
                photo_id=photo_id,
                manual_selection=True,
                notes=record_data.notes,
                recorded_at=(
                    record_data.recorded_at if record_data.recorded_at else func.now()
                ),
            )
            db.add(outfit_record)
            db.flush()  # Get the ID without committing
            logger.info(f"新しいレコードを作成: {outfit_record.id}")

        # Create outfit items and update wardrobe item usage stats
        for clothing_item_id in record_data.clothing_item_ids:
            # Validate clothing_item_id format
            try:
                UUID(clothing_item_id)  # Validate UUID format but keep as string
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"無効なワードローブアイテムIDフォーマット: {clothing_item_id}",
                )

            # Verify clothing item exists (use string comparison for SQLite)
            clothing_item = (
                db.query(ClothingItem)
                .filter(ClothingItem.id == clothing_item_id)
                .first()
            )

            if not clothing_item:
                raise HTTPException(
                    status_code=400,
                    detail=f"ワードローブアイテム {clothing_item_id} が見つかりません",
                )

            # Update wardrobe item usage stats (Issue #921)
            _increment_clothing_usage_count(
                db, clothing_item_id, outfit_record.recorded_at
            )

            outfit_item = OutfitItem(
                outfit_record_id=outfit_record.id,
                clothing_item_id=clothing_item_id,
                manual_added=True,
            )
            db.add(outfit_item)

        # Link external rental items and increment wear counts
        if external_rental_item_ids:
            rental_items = (
                db.query(ExternalRentalItem)
                .filter(ExternalRentalItem.id.in_(external_rental_item_ids))
                .all()
            )
            rentals_by_id = {item.id: item for item in rental_items}
            missing_ids = [
                rental_id
                for rental_id in external_rental_item_ids
                if rental_id not in rentals_by_id
            ]

            if missing_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"レンタルアイテム {missing_ids[0]} が見つかりません",
                )

            recorded_timestamp = outfit_record.recorded_at
            jst_recorded_at = (
                TimezoneUtils.to_jst(recorded_timestamp)
                if isinstance(recorded_timestamp, datetime)
                else jst_now()
            )

            for rental_id in external_rental_item_ids:
                rental_item = rentals_by_id[rental_id]
                link = OutfitExternalRentalItem(
                    outfit_record_id=outfit_record.id,
                    external_rental_item_id=rental_item.id,
                )
                db.add(link)

                rental_item.wear_count = (rental_item.wear_count or 0) + 1
                rental_item.last_worn_at = jst_recorded_at

        db.commit()
        db.refresh(outfit_record)

        # Record co-occurrence data (Issue #1046)
        try:
            if record_data.clothing_item_ids:  # Only record if there are items
                co_occurrence_service = CoOccurrenceService(db)
                capture_date = (
                    outfit_record.recorded_at.date()
                    if outfit_record.recorded_at
                    else None
                )

                co_occurrence_service.record_outfit_wearing(
                    photo_id=record_data.photo_id,
                    worn_item_ids=record_data.clothing_item_ids,
                    capture_date=capture_date,
                    occasion=None,
                    user_rating=None,
                )
                logger.info(
                    f"Co-occurrence data recorded for outfit {outfit_record.id}"
                )
        except ValueError as e:
            logger.warning(f"Invalid data for co-occurrence recording: {e}")
        except Exception as e:
            # Don't fail the entire request if co-occurrence recording fails
            logger.error(f"Failed to record co-occurrence data: {e}", exc_info=True)

        is_update = existing_record is not None
        action = "updated" if is_update else "created"
        return {
            "status": "success",
            "action": action,
            "outfit_record_id": str(outfit_record.id),
            "photo_id": record_data.photo_id,
            "clothing_items_count": len(record_data.clothing_item_ids),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"コーディネート記録の作成に失敗: {e}")
        raise HTTPException(
            status_code=500, detail="コーディネート記録の作成に失敗しました"
        )


# 古い date-range エンドポイントは削除（新しい実装は818行目にあります）


@router.get("/photo/{photo_id}/simple", response_model=SimpleOutfitRecordResponse)
async def get_outfit_record_simple(
    photo_id: str, db: Session = Depends(get_db)
) -> SimpleOutfitRecordResponse:
    """カレンダー表示用のシンプルな outfit record 取得."""
    try:
        # OutfitRecord を取得
        outfit_record = (
            db.query(OutfitRecord).filter(OutfitRecord.photo_id == photo_id).first()
        )

        if not outfit_record:
            return SimpleOutfitRecordResponse(
                id=None,
                photo_id=photo_id,
                clothing_items=[],
                external_rental_item_ids=[],
            )

        # OutfitItem と ClothingItem を JOIN して一度に取得（N+1クエリを回避）
        outfit_items_with_clothing = (
            db.query(OutfitItem, ClothingItem)
            .join(ClothingItem, OutfitItem.clothing_item_id == ClothingItem.id)
            .filter(OutfitItem.outfit_record_id == str(outfit_record.id))
            .all()
        )

        rental_link_ids = [
            str(row[0])
            for row in db.query(OutfitExternalRentalItem.external_rental_item_id)
            .filter(OutfitExternalRentalItem.outfit_record_id == outfit_record.id)
            .all()
        ]

        if not outfit_items_with_clothing:
            return SimpleOutfitRecordResponse(
                id=str(outfit_record.id),
                photo_id=(
                    str(outfit_record.photo_id)
                    if outfit_record.photo_id is not None
                    else None
                ),
                clothing_items=[],
                external_rental_item_ids=rental_link_ids,
            )

        # シンプルなレスポンス構築
        items_response = []
        for outfit_item, clothing_item in outfit_items_with_clothing:

            if clothing_item:
                # Handle both dict and list formats for image_urls
                image_urls_value: Dict[str, Any] = {}
                if (
                    hasattr(clothing_item, "image_urls")
                    and clothing_item.image_urls is not None
                ):
                    # Cast to avoid mypy unreachable code detection
                    image_urls = cast(Union[dict, list, Any], clothing_item.image_urls)
                    if isinstance(image_urls, dict):
                        image_urls_value = image_urls
                    elif isinstance(image_urls, list) and image_urls:
                        # Convert list to dict format
                        image_urls_value = {"original": image_urls[0]}

                clothing_item_response = SimpleClothingItemResponse(
                    id=str(clothing_item.id),
                    name=str(clothing_item.name),
                    category=(
                        clothing_item.category.value
                        if clothing_item.category
                        else "OTHER"
                    ),
                    brand=str(clothing_item.brand) if clothing_item.brand else None,
                    image_urls=image_urls_value,
                )

                outfit_item_response = SimpleOutfitItemResponse(
                    id=str(outfit_item.id), clothing_item=clothing_item_response
                )
                items_response.append(outfit_item_response)

        return SimpleOutfitRecordResponse(
            id=str(outfit_record.id),
            photo_id=(
                str(outfit_record.photo_id)
                if outfit_record.photo_id is not None
                else None
            ),
            clothing_items=items_response,
            external_rental_item_ids=rental_link_ids,
        )

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to get outfit record for photo {photo_id}: {e}")
        raise HTTPException(
            status_code=500, detail="コーディネート記録の取得に失敗しました"
        )


@router.post("/batch/simple", response_model=BatchOutfitResponse)
async def get_outfit_records_batch_simple(
    request: BatchOutfitRequest, db: Session = Depends(get_db)
) -> BatchOutfitResponse:
    """複数写真のシンプルな outfit record をバッチ取得（N+1 問題解決）."""
    try:
        if not request.photo_ids:
            return BatchOutfitResponse(results={})

        # リクエストサイズの制限（大量リクエスト対策）
        if len(request.photo_ids) > 100:
            raise HTTPException(
                status_code=400,
                detail="写真IDが多すぎます。バッチリクエストは最大100枚までです。",
            )

        # バッチで OutfitRecord を取得
        outfit_records = (
            db.query(OutfitRecord)
            .filter(OutfitRecord.photo_id.in_(request.photo_ids))
            .all()
        )

        # photo_id でマッピング
        outfit_record_map = {record.photo_id: record for record in outfit_records}

        # バッチで OutfitItem を取得
        outfit_record_ids = [str(record.id) for record in outfit_records]
        outfit_items = (
            db.query(OutfitItem)
            .filter(OutfitItem.outfit_record_id.in_(outfit_record_ids))
            .all()
        )

        rental_links = (
            db.query(OutfitExternalRentalItem)
            .filter(OutfitExternalRentalItem.outfit_record_id.in_(outfit_record_ids))
            .all()
        )
        rental_links_by_record: Dict[str, List[str]] = {}
        for link in rental_links:
            record_id = str(link.outfit_record_id)
            rental_links_by_record.setdefault(record_id, []).append(
                str(link.external_rental_item_id)
            )

        # outfit_record_id でグルーピング
        outfit_items_by_record: Dict[str, Any] = {}
        for item in outfit_items:
            record_id = str(item.outfit_record_id)
            if record_id not in outfit_items_by_record:
                outfit_items_by_record[record_id] = []
            outfit_items_by_record[record_id].append(item)

        # バッチで ClothingItem を取得（空リストでも安全）
        clothing_item_ids = [item.clothing_item_id for item in outfit_items]
        if clothing_item_ids:
            clothing_items = (
                db.query(ClothingItem)
                .filter(ClothingItem.id.in_(clothing_item_ids))
                .all()
            )
        else:
            clothing_items = []

        # clothing_item_id でマッピング
        clothing_item_map = {str(item.id): item for item in clothing_items}

        # レスポンス構築
        results = {}
        for photo_id in request.photo_ids:
            outfit_record = outfit_record_map.get(photo_id)  # type: ignore[call-overload]

            if not outfit_record:
                # アウトフィット記録が存在しない場合
                results[photo_id] = SimpleOutfitRecordResponse(
                    id=None,
                    photo_id=photo_id,
                    clothing_items=[],
                    external_rental_item_ids=[],
                )
                continue

            # アウトフィットアイテムを取得
            record_outfit_items = outfit_items_by_record.get(str(outfit_record.id), [])

            # レスポンス用アイテムリスト構築
            items_response = []
            for outfit_item in record_outfit_items:
                clothing_item = clothing_item_map.get(outfit_item.clothing_item_id)

                if clothing_item:
                    # Handle both dict and list formats for image_urls
                    image_urls_value: Dict[str, Any] = {}
                    if (
                        hasattr(clothing_item, "image_urls")
                        and clothing_item.image_urls is not None
                    ):
                        # Cast to avoid mypy unreachable code detection
                        image_urls = cast(
                            Union[dict, list, Any], clothing_item.image_urls
                        )
                        if isinstance(image_urls, dict):
                            image_urls_value = image_urls
                        elif isinstance(image_urls, list) and image_urls:
                            # Convert list to dict format
                            image_urls_value = {"original": image_urls[0]}

                    clothing_item_response = SimpleClothingItemResponse(
                        id=str(clothing_item.id),
                        name=str(clothing_item.name),
                        category=(
                            clothing_item.category.value
                            if clothing_item.category
                            else "OTHER"
                        ),
                        brand=str(clothing_item.brand) if clothing_item.brand else None,
                        image_urls=image_urls_value,
                    )

                    outfit_item_response = SimpleOutfitItemResponse(
                        id=str(outfit_item.id), clothing_item=clothing_item_response
                    )
                    items_response.append(outfit_item_response)

            results[photo_id] = SimpleOutfitRecordResponse(
                id=str(outfit_record.id),
                photo_id=outfit_record.photo_id,
                clothing_items=items_response,
                external_rental_item_ids=rental_links_by_record.get(
                    str(outfit_record.id), []
                ),
            )

        return BatchOutfitResponse(results=results)

    except HTTPException:
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to get batch outfit records: {e}")
        raise HTTPException(
            status_code=500, detail="バッチコーディネート記録の取得に失敗しました"
        )


@router.get("/photo/{photo_id}", response_model=Optional[OutfitRecordResponse])
async def get_outfit_record_by_photo(
    photo_id: str, db: Session = Depends(get_db)
) -> Optional[OutfitRecordResponse]:
    """指定された photo_id の着用記録を取得（従来版）."""
    try:
        outfit_record = (
            db.query(OutfitRecord)
            .options(joinedload(OutfitRecord.outfit_items))
            .filter(OutfitRecord.photo_id == photo_id)
            .first()
        )

        if not outfit_record:
            return None

        # Build response with clothing item details
        outfit_items_response = []
        for outfit_item in outfit_record.outfit_items:
            # Get clothing item details
            clothing_item = (
                db.query(ClothingItem)
                .filter(ClothingItem.id == outfit_item.clothing_item_id)
                .first()
            )

            try:
                clothing_item_data = (
                    {
                        "id": str(clothing_item.id),
                        "name": clothing_item.name,
                        "category": (
                            clothing_item.category.value
                            if clothing_item.category
                            else "OTHER"
                        ),
                        "colors_palette": (
                            clothing_item.colors_palette
                            if hasattr(clothing_item, "colors_palette")
                            and clothing_item.colors_palette is not None
                            else None
                        ),
                        "brand": clothing_item.brand,
                        "image_urls": (
                            clothing_item.image_urls
                            if hasattr(clothing_item, "image_urls")
                            and clothing_item.image_urls is not None
                            else []
                        ),
                        "subcategory": clothing_item.subcategory,
                    }
                    if clothing_item
                    else {}
                )
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.error(
                    f"Error serializing clothing item {clothing_item.id if clothing_item else 'None'}: {str(e)}"
                )
                clothing_item_data = {
                    "id": str(clothing_item.id) if clothing_item else "",
                    "name": "エラー",
                    "category": "OTHER",
                    "colors_palette": None,
                    "brand": None,
                    "image_urls": [],
                    "subcategory": None,
                }

            outfit_item_response = OutfitItemResponse(
                id=str(outfit_item.id),
                outfit_record_id=str(outfit_item.outfit_record_id),
                clothing_item_id=str(outfit_item.clothing_item_id),
                detection_confidence=outfit_item.detection_confidence,
                manual_added=outfit_item.manual_added,
                position_x=outfit_item.position_x,
                position_y=outfit_item.position_y,
                created_at=outfit_item.created_at.isoformat(),
                clothing_item=clothing_item_data,
            )
            outfit_items_response.append(outfit_item_response)

        rental_links_with_items = (
            db.query(OutfitExternalRentalItem, ExternalRentalItem)
            .join(
                ExternalRentalItem,
                OutfitExternalRentalItem.external_rental_item_id
                == ExternalRentalItem.id,
            )
            .filter(OutfitExternalRentalItem.outfit_record_id == outfit_record.id)
            .all()
        )

        external_rental_items_response: List[OutfitExternalRentalItemResponse] = []
        for link, rental_item in rental_links_with_items:
            external_rental_items_response.append(
                OutfitExternalRentalItemResponse(
                    id=str(link.id),
                    external_rental_item_id=str(link.external_rental_item_id),
                    created_at=(
                        link.created_at.isoformat()
                        if link.created_at
                        else jst_now().isoformat()
                    ),
                    external_rental_item=ExternalRentalItemBasicResponse(
                        id=str(rental_item.id),
                        source=rental_item.source.value if rental_item.source else None,
                        name=rental_item.name,
                        brand=rental_item.brand,
                        size=rental_item.size,
                        management_number=rental_item.reference_number,
                        return_due_date=(
                            rental_item.return_due_date.isoformat()
                            if rental_item.return_due_date
                            else None
                        ),
                        status=rental_item.status.value if rental_item.status else None,
                        wear_count=rental_item.wear_count,
                        last_worn_at=(
                            rental_item.last_worn_at.isoformat()
                            if rental_item.last_worn_at
                            else None
                        ),
                        image_url=rental_item.image_url,
                    ),
                )
            )

        return OutfitRecordResponse(
            id=str(outfit_record.id),
            photo_id=(
                str(outfit_record.photo_id)
                if outfit_record.photo_id is not None
                else None
            ),
            recorded_at=outfit_record.recorded_at.isoformat(),
            confidence_score=(
                float(outfit_record.confidence_score)
                if outfit_record.confidence_score is not None
                else None
            ),
            manual_selection=bool(outfit_record.manual_selection),
            notes=str(outfit_record.notes) if outfit_record.notes else None,
            created_at=outfit_record.created_at.isoformat(),
            updated_at=outfit_record.updated_at.isoformat(),
            outfit_items=outfit_items_response,
            external_rental_items=external_rental_items_response,
        )

    except Exception as e:
        logger.error(f"コーディネート記録の取得に失敗: {e}")
        raise HTTPException(
            status_code=500, detail="コーディネート記録の取得に失敗しました"
        )


@router.get("/photo/{photo_id}/clothing-items", response_model=List[dict])
async def get_clothing_items_for_photo(
    photo_id: str, db: Session = Depends(get_db)
) -> List[dict[str, Any]]:
    """指定された photo_id に関連する衣類アイテムのリストを取得."""
    try:
        outfit_record = (
            db.query(OutfitRecord).filter(OutfitRecord.photo_id == photo_id).first()
        )

        if not outfit_record:
            return []

        # OutfitItem と ClothingItem を JOIN して一度に取得（N+1クエリを回避）
        outfit_items_with_clothing = (
            db.query(OutfitItem, ClothingItem)
            .join(ClothingItem, OutfitItem.clothing_item_id == ClothingItem.id)
            .filter(OutfitItem.outfit_record_id == outfit_record.id)
            .all()
        )

        clothing_items = []
        for outfit_item, clothing_item in outfit_items_with_clothing:

            if clothing_item:
                try:
                    clothing_items.append(
                        {
                            "id": str(clothing_item.id),
                            "name": clothing_item.name,
                            "category": (
                                clothing_item.category.value
                                if clothing_item.category
                                else "OTHER"
                            ),
                            "colors_palette": (
                                clothing_item.colors_palette
                                if hasattr(clothing_item, "colors_palette")
                                and clothing_item.colors_palette is not None
                                else None
                            ),
                            "brand": clothing_item.brand,
                            "subcategory": clothing_item.subcategory,
                            "image_urls": (
                                clothing_item.image_urls
                                if hasattr(clothing_item, "image_urls")
                                and clothing_item.image_urls is not None
                                else []
                            ),
                        }
                    )
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(
                        f"Error serializing clothing item {clothing_item.id}: {str(e)}"
                    )
                    clothing_items.append(
                        {
                            "id": str(clothing_item.id),
                            "name": "エラー",
                            "category": "OTHER",
                            "colors_palette": None,
                            "brand": None,
                            "subcategory": None,
                            "image_urls": [],
                        }
                    )

        return clothing_items

    except Exception as e:
        logger.error(f"ワードローブアイテムの取得に失敗: {e}")
        raise HTTPException(
            status_code=500,
            detail="ワードローブアイテムの取得に失敗しました",
        )


@router.get("/date-range", response_model=List[OutfitRecordDateRangeResponse])
async def get_outfit_records_by_date_range(
    start_date: str,
    end_date: str,
    response: Response,
    db: Session = Depends(get_db),
) -> List[OutfitRecordDateRangeResponse]:
    """指定期間内のすべてのoutfit recordsを取得（写真なしも含む）."""
    try:
        response.headers["Cache-Control"] = "public, max-age=60"
        response.headers["CDN-Cache-Control"] = "public, max-age=60"
        # 日付範囲をJST datetimeに変換
        start_dt, _ = TimezoneUtils.get_jst_date_range(start_date)
        _, end_dt = TimezoneUtils.get_jst_date_range(end_date)

        # OutfitRecord, OutfitItem, ClothingItem をすべて JOIN して一度に取得
        outfit_data = (
            db.query(OutfitRecord, OutfitItem, ClothingItem)
            .join(OutfitItem, OutfitItem.outfit_record_id == OutfitRecord.id)
            .join(ClothingItem, ClothingItem.id == OutfitItem.clothing_item_id)
            .filter(OutfitRecord.recorded_at >= start_dt)
            .filter(OutfitRecord.recorded_at <= end_dt)
            .order_by(OutfitRecord.recorded_at.desc())
            .all()
        )

        # グループ化してデータを整理
        record_dict: Dict[str, Any] = {}
        for outfit_record, outfit_item, clothing_item in outfit_data:
            record_id = str(outfit_record.id)
            if record_id not in record_dict:
                # SQLAlchemy Column[datetime] を datetime に変換
                recorded_at_datetime = cast(datetime, outfit_record.recorded_at)
                date_key = TimezoneUtils.format_jst_date(recorded_at_datetime)
                record_dict[record_id] = {
                    "date": date_key,
                    "outfit_record_id": record_id,
                    "photo_id": (
                        outfit_record.photo_id if outfit_record.photo_id else None
                    ),
                    "clothing_items": [],
                    "external_rental_item_ids": [],
                    "external_rental_items": [],
                }

            clothing_item_data = DateRangeClothingItemResponse(
                id=str(clothing_item.id),
                name=str(clothing_item.name),
                category=(
                    clothing_item.category.value if clothing_item.category else "OTHER"
                ),
                brand=(str(clothing_item.brand) if clothing_item.brand else None),
                image_urls=(
                    clothing_item.image_urls
                    if hasattr(clothing_item, "image_urls")
                    else {}
                ),
            )
            record_dict[record_id]["clothing_items"].append(clothing_item_data)

        # レコードがない OutfitRecord も取得する必要がある場合
        outfit_records_without_items = (
            db.query(OutfitRecord)
            .outerjoin(OutfitItem, OutfitItem.outfit_record_id == OutfitRecord.id)
            .filter(OutfitRecord.recorded_at >= start_dt)
            .filter(OutfitRecord.recorded_at <= end_dt)
            .filter(OutfitItem.id.is_(None))
            .all()
        )

        # アイテムがない OutfitRecord も追加
        for outfit_record in outfit_records_without_items:
            record_id = str(outfit_record.id)
            if record_id not in record_dict:
                recorded_at_datetime = cast(datetime, outfit_record.recorded_at)
                date_key = TimezoneUtils.format_jst_date(recorded_at_datetime)
                record_dict[record_id] = {
                    "date": date_key,
                    "outfit_record_id": record_id,
                    "photo_id": (
                        outfit_record.photo_id if outfit_record.photo_id else None
                    ),
                    "clothing_items": [],
                    "external_rental_item_ids": [],
                    "external_rental_items": [],
                }

        record_ids = list(record_dict.keys())
        if record_ids:
            rental_links = (
                db.query(OutfitExternalRentalItem)
                .filter(OutfitExternalRentalItem.outfit_record_id.in_(record_ids))
                .all()
            )
            rental_links_by_record: Dict[str, List[str]] = {}
            for link in rental_links:
                record_id = str(link.outfit_record_id)
                rental_links_by_record.setdefault(record_id, []).append(
                    str(link.external_rental_item_id)
                )

            for record_id in record_dict:
                record_dict[record_id]["external_rental_item_ids"] = (
                    rental_links_by_record.get(record_id, [])
                )

            rental_links_with_items = (
                db.query(OutfitExternalRentalItem, ExternalRentalItem)
                .join(
                    ExternalRentalItem,
                    OutfitExternalRentalItem.external_rental_item_id
                    == ExternalRentalItem.id,
                )
                .filter(OutfitExternalRentalItem.outfit_record_id.in_(record_ids))
                .all()
            )
            rental_items_by_record: Dict[str, List[ExternalRentalItemBasicResponse]] = (
                {}
            )
            for link, rental_item in rental_links_with_items:
                record_id = str(link.outfit_record_id)
                rental_items_by_record.setdefault(record_id, []).append(
                    ExternalRentalItemBasicResponse(
                        id=str(rental_item.id),
                        source=(
                            rental_item.source.value if rental_item.source else None
                        ),
                        name=rental_item.name,
                        brand=rental_item.brand,
                        size=rental_item.size,
                        management_number=rental_item.reference_number,
                        return_due_date=(
                            rental_item.return_due_date.isoformat()
                            if rental_item.return_due_date
                            else None
                        ),
                        status=(
                            rental_item.status.value if rental_item.status else None
                        ),
                        wear_count=rental_item.wear_count,
                        last_worn_at=(
                            rental_item.last_worn_at.isoformat()
                            if rental_item.last_worn_at
                            else None
                        ),
                        image_url=rental_item.image_url,
                    )
                )

            for record_id in record_dict:
                record_dict[record_id]["external_rental_items"] = (
                    rental_items_by_record.get(record_id, [])
                )

        # 結果を構築（各レコードの最初の4つのアイテムのみ）
        results = []
        for record_data in record_dict.values():
            # Pydanticモデルとして作成
            outfit_response = OutfitRecordDateRangeResponse(
                date=record_data["date"],
                outfit_record_id=record_data["outfit_record_id"],
                photo_id=record_data["photo_id"],
                clothing_items=record_data["clothing_items"][
                    :4
                ],  # カレンダー表示用に最初の4つのみ
                external_rental_item_ids=record_data["external_rental_item_ids"],
                external_rental_items=record_data["external_rental_items"],
            )
            results.append(outfit_response)

        # 日付でソート
        results.sort(key=lambda x: x.date, reverse=True)

        return results

    except Exception as e:
        logger.error(f"コーディネート記録の取得に失敗: {e}")
        raise HTTPException(
            status_code=500, detail="コーディネート記録の取得に失敗しました"
        )


@router.get("/all", response_model=List[OutfitRecordResponse])
async def get_all_outfit_records(
    limit: int = 50, offset: int = 0, db: Session = Depends(get_db)
) -> List[OutfitRecordResponse]:
    """全ての着用記録を取得（ページネーション対応）."""
    try:
        outfit_records = (
            db.query(OutfitRecord)
            .options(joinedload(OutfitRecord.outfit_items))
            .order_by(OutfitRecord.recorded_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        response = []
        for outfit_record in outfit_records:
            # Build response similar to get_outfit_record_by_photo
            outfit_items_response = []
            for outfit_item in outfit_record.outfit_items:
                clothing_item = (
                    db.query(ClothingItem)
                    .filter(ClothingItem.id == outfit_item.clothing_item_id)
                    .first()
                )

                try:
                    clothing_item_data = (
                        {
                            "id": str(clothing_item.id),
                            "name": clothing_item.name,
                            "category": (
                                clothing_item.category.value
                                if clothing_item.category
                                else "OTHER"
                            ),
                            "colors_palette": (
                                clothing_item.colors_palette
                                if hasattr(clothing_item, "colors_palette")
                                and clothing_item.colors_palette is not None
                                else None
                            ),
                            "brand": clothing_item.brand,
                            "image_urls": (
                                clothing_item.image_urls
                                if hasattr(clothing_item, "image_urls")
                                and clothing_item.image_urls is not None
                                else []
                            ),
                            "subcategory": clothing_item.subcategory,
                        }
                        if clothing_item
                        else {}
                    )
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(
                        f"Error serializing clothing item {clothing_item.id if clothing_item else 'None'}: {str(e)}"
                    )
                    clothing_item_data = {
                        "id": str(clothing_item.id) if clothing_item else "",
                        "name": "エラー",
                        "category": "OTHER",
                        "colors_palette": None,
                        "brand": None,
                        "image_urls": [],
                        "subcategory": None,
                    }

                outfit_item_response = OutfitItemResponse(
                    id=str(outfit_item.id),
                    outfit_record_id=str(outfit_item.outfit_record_id),
                    clothing_item_id=str(outfit_item.clothing_item_id),
                    detection_confidence=outfit_item.detection_confidence,
                    manual_added=outfit_item.manual_added,
                    position_x=outfit_item.position_x,
                    position_y=outfit_item.position_y,
                    created_at=outfit_item.created_at.isoformat(),
                    clothing_item=clothing_item_data,
                )
                outfit_items_response.append(outfit_item_response)

            rental_links_with_items = (
                db.query(OutfitExternalRentalItem, ExternalRentalItem)
                .join(
                    ExternalRentalItem,
                    OutfitExternalRentalItem.external_rental_item_id
                    == ExternalRentalItem.id,
                )
                .filter(OutfitExternalRentalItem.outfit_record_id == outfit_record.id)
                .all()
            )

            external_rental_items_response: List[OutfitExternalRentalItemResponse] = []
            for link, rental_item in rental_links_with_items:
                external_rental_items_response.append(
                    OutfitExternalRentalItemResponse(
                        id=str(link.id),
                        external_rental_item_id=str(link.external_rental_item_id),
                        created_at=(
                            link.created_at.isoformat()
                            if link.created_at
                            else jst_now().isoformat()
                        ),
                        external_rental_item=ExternalRentalItemBasicResponse(
                            id=str(rental_item.id),
                            source=(
                                rental_item.source.value if rental_item.source else None
                            ),
                            name=rental_item.name,
                            brand=rental_item.brand,
                            size=rental_item.size,
                            management_number=rental_item.reference_number,
                            return_due_date=(
                                rental_item.return_due_date.isoformat()
                                if rental_item.return_due_date
                                else None
                            ),
                            status=(
                                rental_item.status.value if rental_item.status else None
                            ),
                            wear_count=rental_item.wear_count,
                            last_worn_at=(
                                rental_item.last_worn_at.isoformat()
                                if rental_item.last_worn_at
                                else None
                            ),
                            image_url=rental_item.image_url,
                        ),
                    )
                )

            outfit_record_response = OutfitRecordResponse(
                id=str(outfit_record.id),
                photo_id=(
                    str(outfit_record.photo_id)
                    if outfit_record.photo_id is not None
                    else None
                ),
                recorded_at=outfit_record.recorded_at.isoformat(),
                confidence_score=(
                    float(outfit_record.confidence_score)
                    if outfit_record.confidence_score is not None
                    else None
                ),
                manual_selection=bool(outfit_record.manual_selection),
                notes=str(outfit_record.notes) if outfit_record.notes else None,
                created_at=outfit_record.created_at.isoformat(),
                updated_at=outfit_record.updated_at.isoformat(),
                outfit_items=outfit_items_response,
                external_rental_items=external_rental_items_response,
            )
            response.append(outfit_record_response)

        return response

    except Exception as e:
        logger.error(f"コーディネート記録の取得に失敗: {e}")
        raise HTTPException(
            status_code=500, detail="コーディネート記録の取得に失敗しました"
        )


@router.delete("/photo/{photo_id}")
async def delete_outfit_record_by_photo(
    photo_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_write_access),
) -> dict[str, Any]:
    """指定した写真のコーディネート記録を削除する.

    写真、記録、AI検出情報を削除するが、ワードローブアイテム自体は削除しない
    コーディネート記録がない写真でも削除可能
    """
    try:
        deleted_items = []

        # OutfitRecord を取得（存在しない場合もある）
        outfit_record = (
            db.query(OutfitRecord).filter(OutfitRecord.photo_id == photo_id).first()
        )

        if outfit_record:
            # Before deleting, decrement usage count for associated items (Issue #921)
            outfit_items = (
                db.query(OutfitItem)
                .filter(OutfitItem.outfit_record_id == outfit_record.id)
                .all()
            )

            for outfit_item in outfit_items:
                _decrement_clothing_usage_count(db, outfit_item.clothing_item_id)

            rental_links = (
                db.query(OutfitExternalRentalItem)
                .filter(OutfitExternalRentalItem.outfit_record_id == outfit_record.id)
                .all()
            )
            if rental_links:
                rental_item_ids = [
                    link.external_rental_item_id for link in rental_links
                ]
                rental_items = (
                    db.query(ExternalRentalItem)
                    .filter(ExternalRentalItem.id.in_(rental_item_ids))
                    .all()
                )
                rentals_by_id = {item.id: item for item in rental_items}
                for link in rental_links:
                    rental_item = rentals_by_id.get(link.external_rental_item_id)
                    if rental_item and rental_item.wear_count:
                        rental_item.wear_count = max(0, rental_item.wear_count - 1)
                        if rental_item.wear_count == 0:
                            rental_item.last_worn_at = None

                db.query(OutfitExternalRentalItem).filter(
                    OutfitExternalRentalItem.outfit_record_id == outfit_record.id
                ).delete()
                deleted_items.append("external_rental_links")

            # OutfitRecord を削除（OutfitItem は cascade で自動削除される）
            db.delete(outfit_record)
            deleted_items.extend(["outfit_record", "outfit_items"])
        else:
            import logging

            logger = logging.getLogger(__name__)
            logger.info(
                f"No outfit record found for photo {photo_id}, proceeding with photo deletion"
            )

        # Photo テーブルから写真も削除（論理削除またはデータベース設計に応じて）
        from ..models import Photo

        photo = db.query(Photo).filter(Photo.id == photo_id).first()
        if photo:
            # 論理削除を使用する場合
            if hasattr(photo, "deleted_at"):
                photo.deleted_at = func.now()
            else:
                # 物理削除
                db.delete(photo)
            deleted_items.append("photo")

        # AI 検出結果も削除（detection_results テーブルがある場合）
        try:
            from ..models import DetectionResult

            detection_results = (
                db.query(DetectionResult)
                .filter(DetectionResult.photo_id == photo_id)
                .all()
            )
            for result in detection_results:
                db.delete(result)
            if detection_results:
                deleted_items.append("ai_detection_results")
        except ImportError:
            # DetectionResult テーブルが存在しない場合はスキップ
            pass

        db.commit()

        return {
            "message": (
                "写真とコーディネート記録を正常に削除しました"
                if deleted_items
                else "削除する項目が見つかりませんでした"
            ),
            "photo_id": photo_id,
            "deleted_items": deleted_items,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to delete outfit record for photo {photo_id}: {e}")
        raise HTTPException(
            status_code=500, detail="コーディネート記録の削除に失敗しました"
        )
