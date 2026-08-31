"""Co-occurrence data API endpoints."""

import logging
from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import Field

from ..schemas.base import BaseModel
from ..database import get_db
from ..co_occurrence_service import CoOccurrenceService
from ..co_occurrence_batch import CoOccurrenceBatchProcessor
from ..co_occurrence_models import ItemPairCoOccurrence
from ..security import require_write_access
from ..wardrobe_models import ClothingItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/co-occurrence", tags=["co-occurrence"])


class ItemMatchResponse(BaseModel):
    """Response for item matching."""

    item_id: str
    name: str
    category: str
    subcategory: Optional[str]
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    co_occurrence_count: int


class CategoryProbabilityRequest(BaseModel):
    """Request for category probability."""

    category_1: str
    category_2: str
    subcategory_1: Optional[str] = None
    subcategory_2: Optional[str] = None
    season: Optional[str] = None


class CategoryProbabilityResponse(BaseModel):
    """Response for category probability."""

    category_1: str
    category_2: str
    subcategory_1: Optional[str]
    subcategory_2: Optional[str]
    season: Optional[str]
    probability: float = Field(..., ge=0.0, le=1.0)


class BatchProcessResponse(BaseModel):
    """Response for batch processing."""

    status: str
    records_processed: int
    new_patterns_found: int
    patterns_updated: int
    processing_time_ms: float


@router.get("/items/{item_id}/best-matches", response_model=List[ItemMatchResponse])
def get_best_matching_items(
    item_id: str,
    limit: int = Query(10, ge=1, le=50, description="Maximum number of results"),
    min_confidence: float = Query(
        0.3, ge=0.0, le=1.0, description="Minimum confidence score"
    ),
    db: Session = Depends(get_db),
):
    """Get best matching items based on co-occurrence data.

    Args:
        item_id: The clothing item ID to find matches for
        limit: Maximum number of results (1-50)
        min_confidence: Minimum confidence score (0.0-1.0)

    """
    # Verify item exists
    item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=404, detail=f"Clothing item {item_id} not found"
        )

    service = CoOccurrenceService(db)
    matches = service.get_best_matching_items(
        item_id=item_id, limit=limit, min_confidence=min_confidence
    )

    results = []
    for matching_item, score in matches:
        # Get actual co-occurrence count from database
        id1, id2 = sorted([item_id, matching_item.id])
        co_occurrence = (
            db.query(ItemPairCoOccurrence)
            .filter(
                ItemPairCoOccurrence.item_id_1 == id1,
                ItemPairCoOccurrence.item_id_2 == id2,
            )
            .first()
        )
        count = co_occurrence.co_occurrence_count if co_occurrence else 0

        results.append(
            ItemMatchResponse(
                item_id=matching_item.id,
                name=matching_item.name,
                category=(
                    matching_item.category.value if matching_item.category else "OTHER"
                ),
                subcategory=matching_item.subcategory,
                confidence_score=score,
                co_occurrence_count=count,
            )
        )

    return results


@router.post("/category-probability", response_model=CategoryProbabilityResponse)
def get_category_probability(
    request: CategoryProbabilityRequest,
    db: Session = Depends(get_db),
):
    """Get co-occurrence probability between two categories."""
    service = CoOccurrenceService(db)

    probability = service.get_category_probability(
        category_1=request.category_1,
        category_2=request.category_2,
        subcategory_1=request.subcategory_1,
        subcategory_2=request.subcategory_2,
        season=request.season,
    )

    return CategoryProbabilityResponse(
        category_1=request.category_1,
        category_2=request.category_2,
        subcategory_1=request.subcategory_1,
        subcategory_2=request.subcategory_2,
        season=request.season,
        probability=probability,
    )


@router.post("/batch/process", response_model=BatchProcessResponse)
def process_batch_update(
    days_back: int = Query(1, ge=1, le=30, description="Days to process"),
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_write_access),
):
    """Run batch processing to update co-occurrence data.

    Args:
        days_back: Number of days to process (1-30)
        target_date: Target date for processing (defaults to yesterday)

    """
    processor = CoOccurrenceBatchProcessor(db)

    try:
        stat = processor.process_daily_batch(
            target_date=target_date, days_back=days_back
        )

        return BatchProcessResponse(
            status=stat.status,
            records_processed=stat.records_processed,
            new_patterns_found=stat.new_patterns_found,
            patterns_updated=stat.patterns_updated,
            processing_time_ms=stat.processing_time_ms or 0.0,
        )
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        raise HTTPException(status_code=500, detail="Batch processing failed")


@router.post("/batch/migrate")
def migrate_existing_data(
    db: Session = Depends(get_db),
    _: None = Depends(require_write_access),
):
    """Migrate all existing outfit data to co-occurrence tables."""
    processor = CoOccurrenceBatchProcessor(db)

    try:
        processor.migrate_existing_data()
        return {"status": "success", "message": "Migration completed successfully"}
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail="Migration failed")
