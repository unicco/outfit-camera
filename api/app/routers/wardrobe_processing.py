"""Wardrobe processing status endpoints."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..wardrobe_models import ClothingItem
from ..schemas.base import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/wardrobe/processing", tags=["wardrobe-processing"])


class ProcessingStatusResponse(BaseModel):
    """Processing status response."""

    item_id: str
    upload_completed: bool
    color_extraction: Optional[str] = None  # pending, completed, failed, skipped
    jina_embedding: Optional[str] = None
    last_updated: Optional[datetime] = None


@router.get("/status/{item_id}", response_model=ProcessingStatusResponse)
async def get_processing_status(
    item_id: str, db: Session = Depends(get_db)
) -> ProcessingStatusResponse:
    """Get processing status for a wardrobe item."""
    item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Check processing status from metadata
    metadata = dict(item.image_metadata) if item.image_metadata else {}

    # Determine status
    color_status = "skipped"
    if "color_distribution" in metadata:
        color_status = "completed"
    elif "color_extraction_failed" in metadata:
        color_status = "failed"

    embedding_status = "skipped"
    if item.embedding_vector:
        embedding_status = "completed"
    elif item.embedding_computed_at is None and item.image_urls:
        embedding_status = "pending"

    return ProcessingStatusResponse(
        item_id=item_id,
        upload_completed=bool(item.image_urls),
        color_extraction=color_status,
        jina_embedding=embedding_status,
        last_updated=item.updated_at,
    )
