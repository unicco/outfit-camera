"""Outfit similarity search endpoints .

Extracted verbatim from the ``api.py`` monolith (now removed). Shared helpers
(``get_db``/``PhotoRepository``) live in their permanent home ``..api_shared``
. ``SIMILARITY_SEARCH_AVAILABLE`` moved here with its
sole consumer.
"""

import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api_shared import PhotoRepository, get_db
from ..services.photo_utils import cosine_similarity_numpy

logger = logging.getLogger(__name__)

# Note: sklearn dependency removed - using numpy implementation
SIMILARITY_SEARCH_AVAILABLE = True

router = APIRouter(prefix="/api/v2", tags=["similarity"])


@router.get("/similar-outfits/{photo_id}", response_model=None)
async def get_similar_outfits(
    photo_id: str, limit: int = 10, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """指定した写真に類似するコーディネートを検索."""
    try:
        if not SIMILARITY_SEARCH_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Similarity search not available (missing dependencies)",
            )

        repo = PhotoRepository(db)

        # ターゲット写真を取得
        target_photo = repo.get_by_id(photo_id)
        if not target_photo:
            raise HTTPException(status_code=404, detail="Photo not found")

        if not target_photo.embedding_vector:
            raise HTTPException(
                status_code=400, detail="Target photo does not have embedding vector"
            )

        # すべての embedding を持つ写真を取得
        all_photos_with_embeddings = repo.get_all_with_embeddings()

        if len(all_photos_with_embeddings) <= 1:
            return {
                "target_photo_id": photo_id,
                "similar_photos": [],
                "message": "Not enough photos with embeddings for comparison",
            }

        # ターゲット写真の embedding
        target_embedding = np.array(target_photo.embedding_vector).reshape(1, -1)

        # 類似度計算
        similar_photos = []
        for photo in all_photos_with_embeddings:
            if photo.id == photo_id:
                continue  # 自分自身をスキップ

            photo_embedding = np.array(photo.embedding_vector).reshape(1, -1)
            similarity = cosine_similarity_numpy(target_embedding, photo_embedding)[0][
                0
            ]

            similar_photos.append(
                {
                    "photo_id": photo.id,
                    "filename": photo.filename,
                    "captured_at": photo.captured_at.isoformat(),
                    "similarity_score": float(similarity),
                    "clothing_items": photo.clothing_items or [],
                    "person_detected": photo.person_detected,
                    "file_path": photo.file_path,
                }
            )

        # 類似度でソート（降順）
        similar_photos.sort(key=lambda x: x["similarity_score"], reverse=True)

        # 上位 limit 件を返す
        similar_photos = similar_photos[:limit]

        return {
            "target_photo_id": photo_id,
            "target_captured_at": target_photo.captured_at.isoformat(),
            "target_clothing_items": target_photo.clothing_items or [],
            "similar_photos": similar_photos,
            "total_compared": len(all_photos_with_embeddings) - 1,
        }

    except Exception as e:
        logger.error(f"Failed to find similar outfits: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to find similar outfits"
        ) from e


@router.get("/outfit-search/test", response_model=None)
async def test_outfit_search() -> dict[str, Any]:
    """テスト用：類似コーディネート検索機能のサンプルレスポンス."""
    return {
        "target_photo_id": "d354dca6-b011-4f56-9616-ff10434093e1",
        "target_captured_at": "2025-01-26T10:00:00",
        "target_clothing_items": ["シャツ", "ジーンズ", "スニーカー"],
        "similar_photos": [
            {
                "photo_id": "01127105-6397-4e24-b6d6-4dcf2818d441",
                "filename": "photo_20250125.jpg",
                "captured_at": "2025-01-25T09:30:00",
                "similarity_score": 0.89,
                "clothing_items": ["シャツ", "チノパン", "スニーカー"],
                "person_detected": True,
                "file_path": "/static/photos/photo_20250125.jpg",
            },
            {
                "photo_id": "example-photo-id-2",
                "filename": "photo_20250124.jpg",
                "captured_at": "2025-01-24T08:45:00",
                "similarity_score": 0.76,
                "clothing_items": ["Tシャツ", "ジーンズ", "ブーツ"],
                "person_detected": True,
                "file_path": "/static/photos/photo_20250124.jpg",
            },
        ],
        "total_compared": 15,
        "search_status": "test_mode",
        "message": "This is a test response. Real similarity search requires photos with embeddings.",
    }
