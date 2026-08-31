"""Miscellaneous leftover endpoints .

Extracted verbatim from the ``api.py`` monolith: the static clothing-model-info
descriptor and the development-only sample-photo seeder. These do not form a
cohesive domain — they are the genuine remainder after status/records/photos/
upload/similarity were carved out. Shared helpers (``get_db``/``DB_AVAILABLE``/
``PhotoRepository``) live in their permanent home ``..api_shared`` (
Phase 1 完了・api.py は削除済).
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api_shared import DB_AVAILABLE, PhotoRepository, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["misc"])


@router.get("/clothing-model-info")
async def get_clothing_model_info() -> dict[str, Any]:
    """Get information about clothing detection model.

    NOTE: The old ClothingDetector has been replaced by V2 AI Detection API
    """
    return {
        "available": True,
        "message": "Clothing detection has been migrated to V2 API",
        "api_version": "v2",
        "endpoint": "/api/v2/ai/detect",
        "model_info": {
            "detection": "Roboflow clothing-segmentation-smmu9",
            "background_removal": "GrabCut (OpenCV)",
            "embedding": "Jina AI API",
            "features": [
                "High accuracy clothing detection",
                "Background removal for individual items",
                "Vector embeddings for similarity matching",
                "Wardrobe item matching",
            ],
        },
        "categories": [
            "tops",
            "bottoms",
            "dresses",
            "outerwear",
            "shoes",
            "accessories",
            "bags",
        ],
    }


@router.post("/test-data/create-sample-photos", response_model=None)
async def create_sample_photos(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Create sample photo data for testing (development only)."""
    if not DB_AVAILABLE or not db:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        repo = PhotoRepository(db)

        # Check if we already have photos
        existing_photos = repo.get_recent(limit=1)
        if existing_photos:
            return {
                "message": "Sample photos already exist",
                "count": len(existing_photos),
            }

        # Create sample photos for testing
        from datetime import timedelta

        sample_photos = []
        base_date = datetime.now()

        for i in range(10):
            # Create photos for the last 10 days
            photo_date = base_date - timedelta(days=i)

            photo = repo.create(
                filename=f"sample_photo_{i}.jpg",
                file_path=f"/static/photos/sample_photo_{i}.jpg",
                source="test",
                captured_at=photo_date,
                person_detected=True,
                confidence_score=0.9,
                clothing_items=["Tシャツ", "ジーンズ"],
                file_size=1024000,
                processing_time_ms=500.0,
                model_version="test",
            )

            # Update with AI detection status
            repo.update(str(photo.id), ai_detection_status="completed")
            sample_photos.append(photo)

        return {
            "message": "Sample photos created successfully",
            "count": len(sample_photos),
            "photos": [
                {"id": str(p.id), "captured_at": p.captured_at.isoformat()}
                for p in sample_photos
            ],
        }

    except Exception as e:
        logger.error(f"Failed to create sample photos: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to create sample photos"
        ) from e
