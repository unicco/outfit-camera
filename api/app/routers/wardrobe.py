"""Wardrobe management API endpoints."""

import asyncio
import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, cast

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from ..database import get_db
from ..image_upload_service import ImageUploadService, get_image_upload_service
from ..security import require_write_access
from ..services import item_color
from ..upload_limits import MAX_IMAGE_UPLOAD_BYTES, read_upload_capped
from ..url_safety import is_allowed_storage_url
from ..wardrobe_models import ClothingCategory, ClothingItem, ClothingStatus
from ..outfit_models import OutfitItem, OutfitRecord
from ..schemas.base import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/wardrobe", tags=["wardrobe"])


def _extract_colors_from_palette(
    colors_palette: Optional[Dict[str, Any]],
) -> tuple[Optional[str], Optional[str]]:
    """Extract primary and secondary colors from colors_palette."""
    if not colors_palette or not isinstance(colors_palette, dict):
        return None, None

    palette = colors_palette.get("palette", [])
    if not isinstance(palette, list) or len(palette) == 0:
        return None, None

    # Sort by position to get primary and secondary colors
    sorted_colors = sorted(palette, key=lambda x: x.get("position", 999))

    primary = sorted_colors[0].get("hex") if len(sorted_colors) > 0 else None
    secondary = sorted_colors[1].get("hex") if len(sorted_colors) > 1 else None

    return primary, secondary


async def _attach_primary_color(
    item: ClothingItem, files: List[UploadFile], primary: Dict[str, Any]
) -> None:
    """primary に採った物撮り写真から主要色を取り、colors_palette に入れる.

    人が手で決めた色は上書きしない。抽出に失敗してもアップロード自体は成功させる
    （色は付加情報で、無くても登録は成り立つ）。
    """
    if item_color.is_manually_set(cast(Optional[Dict[str, Any]], item.colors_palette)):
        return

    # upload_multiple_images は失敗したファイルを黙って飛ばすので、files の並びと
    # uploaded_images の並びは一致しない。primary に採られた 1 枚を filename で引く。
    # 同名が複数あると primary がどれか決まらないので、その時は色を付けない
    filename = primary.get("filename")
    matches = [f for f in files if f.filename == filename]
    if len(matches) != 1:
        return
    source = matches[0]

    try:
        await source.seek(0)
        # 生の read() だとアップロード側の上限を素通りするので同じ上限で読む
        image_data = await read_upload_capped(source, MAX_IMAGE_UPLOAD_BYTES)
        item.colors_palette = cast(
            Any, await asyncio.to_thread(item_color.extract_palette, image_data)
        )
    except Exception as e:
        logger.warning("Color extraction failed for item %s: %s", item.id, e)


def _get_ai_recommendations_for_photo(photo_id: str, db: Session) -> Dict[str, dict]:
    """Get AI recommendations for wardrobe items based on photo AI detection results.

    Returns a dict mapping item_id to recommendation info with ranking and score.
    """
    try:
        from ..models import Photo

        # Get photo with AI detection results
        photo = db.query(Photo).filter(Photo.id == photo_id).first()
        if not photo:
            logger.warning(f"Photo {photo_id} not found")
            return {}

        # Check both snake_case and potential camelCase fields
        ai_results = photo.ai_detection_results
        if not ai_results:
            logger.warning(f"Photo {photo_id} has no AI detection results")
            return {}

        recommendations = {}
        detection_results = ai_results
        logger.debug(f"Detection results type: {type(detection_results)}")
        logger.debug(
            f"Detection results keys: {detection_results.keys() if isinstance(detection_results, dict) else 'not a dict'}"
        )

        # Process each detected item's wardrobe matches
        detected_items = detection_results.get("detected_items", [])
        logger.debug(f"Found {len(detected_items)} detected items")

        for detected_item in detected_items:
            category = detected_item.get("category")
            matches = detected_item.get("wardrobe_match_candidates", [])
            logger.debug(f"Category {category}: {len(matches)} matches")

            # Rank matches for this category (top 3)
            for idx, match in enumerate(matches[:3]):
                item_id = (
                    match.get("wardrobe_item_id")  # v2 API uses this field
                    or match.get("clothing_item_id")
                    or match.get("item_id")
                    or match.get("id")
                )

                if item_id:
                    recommendations[item_id] = {
                        "ranking": idx + 1,  # 1-3 for top 3
                        "match_score": match.get("similarity_score", 0.0),
                        "category": category,
                    }
                    logger.debug(
                        f"Added recommendation for item {item_id}: rank {idx + 1}, score {match.get('similarity_score', 0.0):.3f}"
                    )

        return recommendations

    except Exception as e:
        logger.error(
            f"Failed to get AI recommendations for photo {photo_id}: {e}", exc_info=True
        )
        return {}


# Pydantic models for API
class ClothingItemCreate(BaseModel):
    """Request model for creating a clothing item."""

    name: str
    category: str
    subcategory: Optional[str] = None
    brand: Optional[str] = None
    colors_palette: Optional[Dict[str, Any]] = None  # 5色パレット
    pattern: Optional[str] = None
    material: Optional[str] = None
    size: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    purchase_location: Optional[str] = None
    # Sale information (issue #823)
    sale_platform: Optional[str] = None  # mercari, zozoused, etc.
    sale_price: Optional[float] = None
    sale_commission: Optional[float] = None
    disposal_date: Optional[str] = None
    season: Optional[List[str]] = None
    occasion: Optional[List[str]] = None
    care_instructions: Optional[str] = None
    status: Optional[str] = None  # Status field for updates
    tags: Optional[List[str]] = None
    # Wear history fields
    last_used_date: Optional[str] = None
    default_usage_count: Optional[int] = None
    usage_count: Optional[int] = None  # 手動調整用フィールドを追加
    season_suitability: Optional[Dict[str, float]] = None
    weather_suitability: Optional[Dict[str, float]] = None


class SaleInfoUpdate(BaseModel):
    """Request model for updating sale information (issue #823)."""

    sale_platform: Optional[str] = None  # mercari, zozoused, etc.
    sale_price: Optional[float] = None
    sale_commission: Optional[float] = None
    disposal_date: Optional[str] = None  # ISO date string


class ClothingItemResponse(BaseModel):
    """Response model for clothing item."""

    id: str
    name: str
    category: str
    subcategory: Optional[str]
    brand: Optional[str]
    colors_palette: Optional[Dict[str, Any]] = None  # 5色パレット
    # color_primary: Optional[str] = None  # 後方互換性のため計算される
    # color_secondary: Optional[str] = None  # 後方互換性のため計算される
    pattern: Optional[str]
    material: Optional[str]
    size: Optional[str]
    purchase_date: Optional[str]
    purchase_price: Optional[float]
    purchase_location: Optional[str]
    # Sale information (issue #823)
    sale_platform: Optional[str] = None
    sale_price: Optional[float] = None
    sale_commission: Optional[float] = None
    disposal_date: Optional[str] = None
    # Calculated sale fields
    sale_net_amount: Optional[float] = None  # 売却手取り金額
    sale_profit_loss: Optional[float] = None  # 売却損益
    season: Optional[List[str]]
    occasion: Optional[List[str]]
    care_instructions: Optional[str]
    status: str
    image_urls: Optional[Union[Dict[str, Any], List[str]]]
    image_metadata: Optional[dict] = None
    tags: Optional[List[str]]
    # Wear history fields
    last_used_date: Optional[str] = None
    default_usage_count: Optional[int] = None
    usage_count: Optional[int] = None  # システム着用回数
    season_suitability: Optional[Dict[str, float]] = None
    weather_suitability: Optional[Dict[str, float]] = None

    # Jina AI embedding fields
    embedding_vector: Optional[List[float]] = None
    embedding_computed_at: Optional[datetime] = None
    embedding_model_version: Optional[str] = None

    # Calculated fields
    wear_count: int = 0  # Total wear count (default_usage_count + usage_count)
    cost_per_wear: Optional[float] = None
    last_worn: Optional[str] = None  # Frontend compatibility field for last_used_date
    created_at: datetime
    updated_at: datetime

    # AI recommendation fields (populated when photo_id is provided)
    ai_ranking: Optional[int] = None  # 1-3 for top recommendations
    ai_match_score: Optional[float] = None  # Similarity score
    is_ai_recommended: Optional[bool] = None  # True if in top 3


class ImageUploadResponse(BaseModel):
    """Response model for image upload."""

    item_id: str
    uploaded_images: List[dict]


def item_to_response(item: ClothingItem) -> ClothingItemResponse:
    """Convert ClothingItem model to response model, handling ENUMs."""
    # Calculate total wear count
    total_wear_count = (item.default_usage_count or 0) + (item.usage_count or 0)

    # Calculate cost per wear using issue #823 logic
    cost_per_wear = item.cost_per_wear

    # Extract colors from colors_palette for backward compatibility
    primary_color, secondary_color = _extract_colors_from_palette(
        dict(item.colors_palette) if item.colors_palette else None
    )

    return ClothingItemResponse(
        id=str(item.id),
        name=cast(str, item.name),
        category=cast(str, item.category.value if item.category else "OTHER"),
        subcategory=cast(Optional[str], item.subcategory),
        brand=cast(Optional[str], item.brand),
        colors_palette=cast(Optional[Dict[str, Any]], item.colors_palette),
        pattern=cast(Optional[str], item.pattern),
        material=cast(Optional[str], item.material),
        size=cast(Optional[str], item.size),
        purchase_date=item.purchase_date.isoformat() if item.purchase_date else None,
        purchase_price=cast(Optional[float], item.purchase_price),
        purchase_location=cast(Optional[str], item.purchase_location),
        # Sale information (issue #823)
        sale_platform=cast(Optional[str], item.sale_platform),
        sale_price=cast(Optional[float], item.sale_price),
        sale_commission=cast(Optional[float], item.sale_commission),
        disposal_date=item.disposal_date.isoformat() if item.disposal_date else None,
        sale_net_amount=item.sale_net_amount,
        sale_profit_loss=item.sale_profit_loss,
        season=cast(Optional[List[str]], item.season),
        occasion=cast(Optional[List[str]], item.occasion),
        care_instructions=cast(Optional[str], item.care_instructions),
        status=cast(str, item.status.value if item.status else "ACTIVE"),
        image_urls=cast(Optional[Union[Dict[str, Any], List[str]]], item.image_urls),
        image_metadata=cast(Optional[dict], item.image_metadata),
        tags=cast(Optional[List[str]], item.tags),
        last_used_date=item.last_used_date.isoformat() if item.last_used_date else None,
        default_usage_count=cast(Optional[int], item.default_usage_count),
        usage_count=cast(Optional[int], item.usage_count),
        season_suitability=cast(
            Optional[Dict[str, float]],
            (
                item.season_suitability
                if isinstance(item.season_suitability, dict)
                else None
            ),
        ),
        weather_suitability=cast(
            Optional[Dict[str, float]],
            (
                item.weather_suitability
                if isinstance(item.weather_suitability, dict)
                else None
            ),
        ),
        # Jina AI embedding fields
        embedding_vector=cast(Optional[List[float]], item.embedding_vector),
        embedding_computed_at=cast(Optional[datetime], item.embedding_computed_at),
        embedding_model_version=cast(Optional[str], item.embedding_model_version),
        wear_count=int(total_wear_count),
        cost_per_wear=float(cost_per_wear) if cost_per_wear is not None else None,
        last_worn=(
            item.last_used_date.isoformat() if item.last_used_date else None
        ),  # Frontend compatibility
        created_at=cast(datetime, item.created_at),
        updated_at=cast(datetime, item.updated_at),
        # AI recommendation fields (will be set later if applicable)
        ai_ranking=None,
        ai_match_score=None,
        is_ai_recommended=None,
    )


@router.get("/items", response_model=List[ClothingItemResponse])
async def get_wardrobe_items(
    category: Optional[str] = None,
    status: Optional[str] = None,
    photo_id: Optional[str] = None,  # For AI recommendations
    recorded_date: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[ClothingItemResponse]:
    """Get all clothing items, optionally filtered by category and status.

    If photo_id is provided, items will include AI recommendation rankings.
    """
    query = db.query(ClothingItem)

    parsed_recorded_date = None
    if recorded_date:
        try:
            parsed_recorded_date = datetime.strptime(recorded_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid recorded_date format. Use YYYY-MM-DD",
            )

    # Apply status filter only if specified
    if status:
        status_enum = ClothingStatus(status)
        query = query.filter(ClothingItem.status == status_enum)

    if category:
        category_enum = ClothingCategory(category.upper())
        query = query.filter(ClothingItem.category == category_enum)

    if parsed_recorded_date:
        query = query.filter(
            or_(
                ClothingItem.purchase_date.is_(None),
                ClothingItem.purchase_date <= parsed_recorded_date,
            )
        ).filter(
            or_(
                ClothingItem.disposal_date.is_(None),
                ClothingItem.disposal_date >= parsed_recorded_date,
            )
        )

    try:
        items = query.all()
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("Wardrobe item query failed (likely schema mismatch): %s", exc)
        db.rollback()
        return []

    # Get AI recommendations if photo_id is provided
    ai_recommendations = {}
    if photo_id:
        ai_recommendations = _get_ai_recommendations_for_photo(photo_id, db)
        logger.info(
            f"Got {len(ai_recommendations)} AI recommendations for photo {photo_id}"
        )
        if ai_recommendations:
            logger.info(f"Recommendation IDs: {list(ai_recommendations.keys())[:5]}")

    # Convert items to response and add AI recommendation info
    responses = []
    matched_count = 0
    for item in items:
        response = item_to_response(item)

        # Add AI recommendation ranking if available
        item_id = str(item.id)
        if item_id in ai_recommendations:
            matched_count += 1
            # Add recommendation info to response
            recommendation = ai_recommendations[item_id]
            response.ai_ranking = recommendation.get("ranking", 99)
            response.ai_match_score = recommendation.get("match_score", 0.0)
            response.is_ai_recommended = recommendation.get("ranking", 99) <= 3  # Top 3
            logger.debug(
                f"Item {item_id} ({response.name}) has AI recommendation: rank={response.ai_ranking}, score={response.ai_match_score:.3f}"
            )

        responses.append(response)

    logger.info(
        f"Matched {matched_count} items with AI recommendations out of {len(items)} total items"
    )

    # Sort by AI ranking if recommendations exist
    if ai_recommendations:
        responses.sort(key=lambda x: x.ai_ranking if x.ai_ranking is not None else 99)

    return responses


@router.post("/items", response_model=ClothingItemResponse)
async def create_clothing_item(
    item_data: ClothingItemCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_write_access),
) -> ClothingItemResponse:
    """Create a new clothing item."""
    # Parse purchase date if provided
    purchase_date = None
    if item_data.purchase_date:
        try:
            purchase_date = datetime.strptime(
                item_data.purchase_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid purchase date format. Use YYYY-MM-DD"
            )

    # Parse disposal date if provided
    disposal_date = None
    if item_data.disposal_date:
        try:
            disposal_date = datetime.strptime(
                item_data.disposal_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid disposal date format. Use YYYY-MM-DD"
            )

    # Create new item
    new_item = ClothingItem(
        name=item_data.name,
        category=ClothingCategory(item_data.category.upper()),
        subcategory=item_data.subcategory,
        brand=item_data.brand,
        colors_palette=item_data.colors_palette,
        pattern=item_data.pattern,
        material=item_data.material,
        size=item_data.size,
        purchase_date=purchase_date,
        purchase_price=item_data.purchase_price,
        purchase_location=item_data.purchase_location,
        season=item_data.season,
        occasion=item_data.occasion,
        care_instructions=item_data.care_instructions,
        tags=item_data.tags,
        default_usage_count=item_data.default_usage_count,
        usage_count=item_data.usage_count,
        season_suitability=item_data.season_suitability,
        weather_suitability=item_data.weather_suitability,
        disposal_date=disposal_date,
    )

    db.add(new_item)
    db.commit()
    db.refresh(new_item)

    return item_to_response(new_item)


@router.get("/items/{item_id}", response_model=ClothingItemResponse)
async def get_clothing_item(
    item_id: str, db: Session = Depends(get_db)
) -> ClothingItemResponse:
    """Get a specific clothing item by ID."""
    item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    return item_to_response(item)


@router.put("/items/{item_id}", response_model=ClothingItemResponse)
async def update_clothing_item(
    item_id: str,
    item_data: ClothingItemCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_write_access),
) -> ClothingItemResponse:
    """Update a clothing item."""
    logger.info(f"🔄 UPDATE START: item_id={item_id}, new_status={item_data.status}")

    item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()

    if not item:
        logger.error(f"❌ Item not found: {item_id}")
        raise HTTPException(status_code=404, detail="Item not found")

    logger.info(f"📋 BEFORE UPDATE: item.name={item.name}, item.status={item.status}")

    # Parse purchase date if provided
    purchase_date = None
    if item_data.purchase_date:
        try:
            purchase_date = datetime.strptime(
                item_data.purchase_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid purchase date format. Use YYYY-MM-DD"
            )

    # Parse last used date if provided
    last_used_date = None
    if item_data.last_used_date:
        try:
            last_used_date = datetime.strptime(
                item_data.last_used_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid last used date format. Use YYYY-MM-DD"
            )

    # Parse disposal date if provided
    disposal_date = None
    if item_data.disposal_date:
        try:
            disposal_date = datetime.strptime(
                item_data.disposal_date, "%Y-%m-%d"
            ).date()
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid disposal date format. Use YYYY-MM-DD"
            )

    # Update fields using cast for SQLAlchemy compatibility
    item.name = cast(Any, item_data.name)
    item.category = cast(Any, ClothingCategory(item_data.category.upper()))
    item.subcategory = cast(Any, item_data.subcategory)
    item.brand = cast(Any, item_data.brand)
    item.colors_palette = cast(Any, item_data.colors_palette)
    item.pattern = cast(Any, item_data.pattern)
    item.material = cast(Any, item_data.material)
    item.size = cast(Any, item_data.size)
    item.purchase_date = cast(Any, purchase_date)
    item.purchase_price = cast(Any, item_data.purchase_price)
    item.purchase_location = cast(Any, item_data.purchase_location)
    # 売却情報も本エンドポイントで一括更新（null で確実にクリア・issue #823 の別 API は廃止）
    item.sale_platform = cast(Any, item_data.sale_platform)
    item.sale_price = cast(Any, item_data.sale_price)
    item.sale_commission = cast(Any, item_data.sale_commission)
    item.disposal_date = cast(Any, disposal_date)
    item.last_used_date = cast(Any, last_used_date)
    item.season = cast(Any, item_data.season)
    item.occasion = cast(Any, item_data.occasion)
    item.care_instructions = cast(Any, item_data.care_instructions)
    item.tags = cast(Any, item_data.tags)
    item.season_suitability = cast(Any, item_data.season_suitability)
    item.weather_suitability = cast(Any, item_data.weather_suitability)

    # 着用回数の更新
    if item_data.default_usage_count is not None:
        item.default_usage_count = cast(Any, item_data.default_usage_count)
    if item_data.usage_count is not None:
        item.usage_count = cast(Any, item_data.usage_count)

    # Update status if provided
    if item_data.status:
        try:
            old_status = item.status
            item.status = cast(Any, ClothingStatus(item_data.status.upper()))
            logger.info(f"🔄 STATUS UPDATE: {old_status} -> {item.status}")
        except ValueError:
            logger.error(f"❌ Invalid status value: {item_data.status}")
            raise HTTPException(
                status_code=400, detail=f"Invalid status value: {item_data.status}"
            )

    logger.info("💾 Committing to database...")
    db.commit()

    logger.info("🔍 Refreshing item from database...")
    db.refresh(item)

    logger.info(f"✅ AFTER UPDATE: item.name={item.name}, item.status={item.status}")

    # Verify item still exists
    verify_item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
    if not verify_item:
        logger.error(f"💥 CRITICAL: Item disappeared after update! item_id={item_id}")
    else:
        logger.info(f"✅ VERIFIED: Item still exists with status={verify_item.status}")

    return item_to_response(item)


@router.delete("/items/{item_id}")
async def delete_clothing_item(
    item_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_write_access),
) -> dict:
    """Soft delete a clothing item by changing its status."""
    item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Soft delete by changing status
    item.status = cast(Any, ClothingStatus.DISPOSED)
    db.commit()

    return {"message": "Item deleted successfully", "item_id": str(item_id)}


@router.post("/items/{item_id}/images", response_model=ImageUploadResponse)
async def upload_item_images(
    item_id: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    upload_service: ImageUploadService = Depends(get_image_upload_service),
    _: None = Depends(require_write_access),
) -> ImageUploadResponse:
    """Upload images for a clothing item."""
    # Check if item exists
    item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Validate file types
    allowed_content_types = ["image/jpeg", "image/png", "image/webp"]
    for file in files:
        if file.content_type not in allowed_content_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}",
            )

    # Upload images
    try:
        uploaded_images = await upload_service.upload_multiple_images(
            files, str(item_id)
        )
    except Exception as e:
        logger.error(f"Image upload failed for item {item_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Image upload failed")

    # Update item with new image URLs
    from ..utils.timezone_utils import TimezoneUtils

    current_metadata = dict(item.image_metadata) if item.image_metadata else {}
    existing_images = current_metadata.get("images", [])
    if not isinstance(existing_images, list):
        existing_images = []

    existing_images.extend(uploaded_images)
    current_metadata["images"] = existing_images
    current_metadata["updated_at"] = TimezoneUtils.now_jst().isoformat()
    item.image_metadata = cast(Any, current_metadata)

    # Set primary image_urls if not yet set
    if uploaded_images:
        primary = uploaded_images[0]
        if isinstance(primary, dict):
            original_url = primary.get("original_url")
            thumbnails = primary.get("thumbnails", {})
            if original_url or thumbnails:
                item.image_urls = cast(
                    Any,
                    {
                        "original": original_url,
                        "thumbnails": (
                            thumbnails if isinstance(thumbnails, dict) else {}
                        ),
                    },
                )

            await _attach_primary_color(item, files, primary)

    db.commit()

    return ImageUploadResponse(
        item_id=str(item_id),
        uploaded_images=uploaded_images,
        message="Images uploaded successfully",
    )


@router.get("/categories")
async def get_wardrobe_categories() -> dict:
    """Get list of available wardrobe categories."""
    categories = [
        {
            "value": category.value,
            "label": category.value.capitalize(),
            "count": 0,  # Will be populated if needed
        }
        for category in ClothingCategory
    ]

    return {"categories": categories}


@router.get("/items/{item_id}/wear-history")
async def get_item_wear_history(item_id: str, db: Session = Depends(get_db)) -> dict:
    """Get wearing history for a specific clothing item."""
    # Check if item exists
    item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Query outfit_items and outfit_records to get actual wearing history
    wear_records = (
        db.query(OutfitRecord, OutfitItem)
        .join(OutfitItem, OutfitRecord.id == OutfitItem.outfit_record_id)
        .filter(OutfitItem.clothing_item_id == item_id)
        .order_by(OutfitRecord.recorded_at.desc())
        .all()
    )

    # Build wear history list
    # recorded_at は timezone-aware（DateTime(timezone=True)）で保存されるため、
    # JST 日付でフォーマットしてカレンダー側の日付グルーピングと一致させる
    # （UTC のまま .date() すると深夜帯で 1 日ずれる）
    from ..utils.timezone_utils import TimezoneUtils

    wear_history = []
    for outfit_record, outfit_item in wear_records:
        recorded_at = cast(Optional[datetime], outfit_record.recorded_at)
        date_key = TimezoneUtils.format_jst_date(recorded_at) if recorded_at else None
        wear_history.append(
            {
                "date": date_key,
                "outfitRecordId": str(outfit_record.id),
                "photoId": outfit_record.photo_id,
            }
        )

    # Calculate total wears from database
    total_wears = (item.default_usage_count or 0) + (item.usage_count or 0)

    # Get last worn date
    last_worn = item.last_used_date.isoformat() if item.last_used_date else None

    return {
        "wearHistory": wear_history,
        "totalWears": total_wears,
        "lastWorn": last_worn,
    }


@router.get("/items/{item_id}/images")
async def get_item_images(item_id: str, db: Session = Depends(get_db)) -> dict:
    """Get all images for a specific clothing item."""
    # Check if item exists
    item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Extract images from image_metadata
    images = []
    if item.image_metadata and "images" in item.image_metadata:
        for img in item.image_metadata["images"]:  # type: ignore[attr-defined]
            image_data = {
                "id": img.get("id"),
                "original_url": img.get("original_url"),
                "thumbnails": img.get("thumbnails", {}),
                "uploaded_at": item.image_metadata.get(
                    "updated_at", item.created_at.isoformat()
                ),
            }
            images.append(image_data)

    return {"images": images}


@router.get("/items/{item_id}/image-proxy", response_model=None)
async def get_image_proxy(item_id: str, db: Session = Depends(get_db)):
    """Proxy image requests to avoid CORS issues in color picker."""
    import requests

    # StreamingResponse imported at module level

    try:
        # Get the clothing item
        clothing_item = (
            db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
        )
        if not clothing_item:
            raise HTTPException(status_code=404, detail="Clothing item not found")

        # Extract image URL (handle both dict and array formats)
        image_url = None
        image_urls = cast(
            Union[Dict[str, Any], List[str], Any], clothing_item.image_urls
        )
        if image_urls:
            if isinstance(image_urls, dict):
                image_url = image_urls.get("original")
            elif isinstance(image_urls, list) and len(image_urls) > 0:
                image_url = image_urls[0]

        if not image_url:
            raise HTTPException(status_code=404, detail="No image found for this item")

        # If it's a Google Cloud Storage URL, proxy it (SSRF: allowlist のみ)
        if is_allowed_storage_url(image_url):
            response = requests.get(
                image_url, stream=True, timeout=10, allow_redirects=False
            )
            response.raise_for_status()

            return StreamingResponse(
                io.BytesIO(response.content),
                media_type=response.headers.get("Content-Type", "image/jpeg"),
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET",
                    "Access-Control-Allow-Headers": "*",
                },
            )
        else:
            # For local files, redirect to the original URL
            return {"redirect_url": image_url}

    except requests.RequestException as e:
        logger.error(f"Failed to fetch image via proxy: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch image") from e
    except Exception as e:
        logger.error(f"Image proxy error: {e}")
        raise HTTPException(status_code=500, detail="Image proxy error") from e


@router.put("/items/{item_id}/sale-info")
async def update_sale_info(
    item_id: str,
    sale_info: SaleInfoUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_write_access),
) -> dict[str, str]:
    """売却情報を更新（issue #823）."""
    try:
        logger.info(f"🔄 UPDATE SALE INFO: item_id={item_id}, sale_info={sale_info}")

        # アイテムを取得
        item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
        if not item:
            logger.error(f"❌ Item not found: {item_id}")
            raise HTTPException(status_code=404, detail="Item not found")

        logger.info(
            f"📋 BEFORE UPDATE: sale_price={item.sale_price}, sale_platform={item.sale_platform}"
        )

        # 売却情報を更新
        if sale_info.sale_platform is not None:
            logger.info(
                f"🔧 Updating sale_platform: {item.sale_platform} -> {sale_info.sale_platform}"
            )
            item.sale_platform = cast(Any, sale_info.sale_platform)
        if sale_info.sale_price is not None:
            logger.info(
                f"🔧 Updating sale_price: {item.sale_price} -> {sale_info.sale_price}"
            )
            item.sale_price = cast(Any, sale_info.sale_price)
        if sale_info.sale_commission is not None:
            logger.info(
                f"🔧 Updating sale_commission: {item.sale_commission} -> {sale_info.sale_commission}"
            )
            item.sale_commission = cast(Any, sale_info.sale_commission)
        if sale_info.disposal_date is not None:
            if sale_info.disposal_date == "":
                logger.info("🔧 Clearing disposal_date")
                item.disposal_date = cast(Any, None)
            else:
                try:
                    from datetime import datetime

                    new_date = datetime.fromisoformat(sale_info.disposal_date).date()
                    logger.info(
                        f"🔧 Updating disposal_date: {item.disposal_date} -> {new_date}"
                    )
                    item.disposal_date = cast(Any, new_date)
                except ValueError:
                    logger.error(f"❌ Invalid date format: {sale_info.disposal_date}")
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid date format. Use ISO format (YYYY-MM-DD)",
                    )

        # ステータスは編集画面のドロップダウン（メイン PUT）で明示指定した値のみを尊重する。
        # ここで処分情報から status を自動 DISPOSED にすると、アクティブへ戻す操作を打ち消すため廃止。
        logger.info("💾 Committing changes to database...")
        db.commit()

        logger.info(
            f"🔍 AFTER UPDATE: sale_price={item.sale_price}, sale_platform={item.sale_platform}"
        )
        logger.info(f"✅ Updated sale info for item {item_id}")

        return {"message": "売却情報を更新しました"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update sale info for item {item_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update sale info")
