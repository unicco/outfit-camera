"""Pydantic schemas for recommendation APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseModel


class RecommendationContextModel(BaseModel):
    current_season: str
    target_formality: str
    weather_condition: str
    temperature: Optional[float]
    occasion: Optional[str]
    user_schedule: List[str]
    formality_reason: Optional[str] = None
    layer_requirement: Optional[str] = None
    temperature_reason: Optional[str] = None


class RecommendationItemModel(BaseModel):
    item_id: str
    name: str
    category: str
    score: float
    formality: Dict[str, float]
    season: Dict[str, float]
    weather: Dict[str, float]
    rationale: List[str]
    image_urls: Optional[Any] = None


class OutfitRecommendationModel(BaseModel):
    recommendation_id: str
    score: float
    items: List[RecommendationItemModel]
    suggested_for: str
    rationale: List[str]


class TPORecommendationRequest(BaseModel):
    weather: Optional[str] = None
    temperature: Optional[float] = None
    occasion: Optional[str] = None
    user_schedule: Optional[List[str]] = None
    limit: int = 5


class TPORecommendationResponse(BaseModel):
    generated_at: datetime
    context: RecommendationContextModel
    weather: Dict[str, Any]
    recommendations: List[OutfitRecommendationModel]
