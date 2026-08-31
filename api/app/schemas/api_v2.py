"""Shared API v2 response models .

Permanent home for the response models that lived in the ``api.py`` monolith.

Note: relocating these changes their OpenAPI component names from
``app__api__PhotoResponse`` / ``app__api__RecordResponse`` to
``app__schemas__api_v2__PhotoResponse`` / ``...RecordResponse``. The URL/method
surface (guarded by the route snapshot) is unchanged; only the internal component
schema names in the generated OpenAPI document differ.
"""

from datetime import datetime

from .base import BaseModel


class PhotoResponse(BaseModel):
    """Simplified photo response."""

    id: str
    filename: str
    captured_at: datetime  # 正しい命名：撮影日時
    person_detected: bool
    confidence_score: float | None
    clothing_items: list[str]
    source: str
    ai_detection_status: str | None = None
    ai_detection_results: dict | None = None  # AI検出結果の詳細
    photo_url: str | None = None  # GCS URL を追加


class RecordResponse(BaseModel):
    """Record response matching frontend expectations."""

    id: str
    date: str
    timestamp: str
    photo_id: str
    photo_url: str | None = None
    person_detected: bool
    clothing_items: list[str]
    notes: str | None = None  # Always None in v2
