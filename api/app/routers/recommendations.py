"""Recommendation API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..settings import Settings, get_settings
from ..services.environment import WeatherService, WeatherSnapshot
from ..services.tpo_recommendation import (
    OutfitRecommendationData,
    RecommendationContext,
    TPORecommendationService,
)
from ..schemas.recommendations import (
    OutfitRecommendationModel,
    RecommendationContextModel,
    RecommendationItemModel,
    TPORecommendationRequest,
    TPORecommendationResponse,
)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.post("/tpo", response_model=TPORecommendationResponse)
async def get_tpo_recommendations(
    payload: TPORecommendationRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TPORecommendationResponse:
    weather_service = WeatherService(settings)
    weather_snapshot: WeatherSnapshot | None = None

    weather_condition = payload.weather
    temperature = payload.temperature

    if weather_condition is None or temperature is None:
        weather_snapshot = await weather_service.get_current_weather()
        weather_condition = weather_condition or weather_snapshot.condition
        temperature = (
            temperature if temperature is not None else weather_snapshot.temperature
        )

    service = TPORecommendationService(db, settings)
    context = service.build_context(
        weather=weather_condition,
        temperature=temperature,
        occasion=payload.occasion,
        user_schedule=payload.user_schedule,
    )

    recommendations = service.recommend_outfits(
        context=context,
        weather_snapshot=weather_snapshot,
        limit=payload.limit,
    )

    weather_payload = _weather_payload(weather_condition, temperature, weather_snapshot)

    return TPORecommendationResponse(
        generated_at=datetime.utcnow().replace(tzinfo=timezone.utc),
        context=_context_to_model(context),
        weather=weather_payload,
        recommendations=_convert_recommendations(recommendations),
    )


# --- helper conversions ---------------------------------------------------


def _context_to_model(context: RecommendationContext) -> RecommendationContextModel:
    return RecommendationContextModel(
        current_season=context.current_season,
        target_formality=context.target_formality,
        weather_condition=context.weather_condition,
        temperature=context.temperature,
        occasion=context.occasion,
        user_schedule=list(context.user_schedule),
        formality_reason=context.formality_reason,
        layer_requirement=context.layer_requirement,
        temperature_reason=context.temperature_reason,
    )


def _convert_recommendations(
    outfits: List[OutfitRecommendationData],
) -> List[OutfitRecommendationModel]:
    response: List[OutfitRecommendationModel] = []
    for idx, outfit in enumerate(outfits, start=1):
        items = [
            RecommendationItemModel(
                item_id=str(entry.item.id),
                name=entry.item.name,
                category=(
                    entry.item.category.value if entry.item.category else "UNKNOWN"
                ),
                score=entry.score,
                formality=entry.formality,
                season=entry.season,
                weather=entry.weather,
                rationale=entry.rationale,
                image_urls=entry.item.image_urls,
            )
            for entry in outfit.items
        ]
        response.append(
            OutfitRecommendationModel(
                recommendation_id=f"outfit-{idx}",
                score=outfit.score,
                items=items,
                suggested_for=outfit.suggested_for,
                rationale=outfit.rationale,
            )
        )
    return response


def _weather_payload(
    condition: str | None,
    temperature: float | None,
    snapshot: WeatherSnapshot | None,
) -> Dict[str, Any]:
    if snapshot is None:
        return {
            "condition": condition or "unknown",
            "temperature": temperature,
            "precipitation_mm": None,
            "umbrella_required": False,
        }

    return {
        "condition": snapshot.condition,
        "temperature": snapshot.temperature,
        "feels_like": snapshot.feels_like,
        "temp_min": snapshot.temp_min,
        "temp_max": snapshot.temp_max,
        "precipitation_mm": snapshot.precipitation_mm,
        "humidity": snapshot.humidity,
        "wind_speed": snapshot.wind_speed,
        "umbrella_required": snapshot.umbrella_required,
        "sunrise": snapshot.sunrise.isoformat() if snapshot.sunrise else None,
        "sunset": snapshot.sunset.isoformat() if snapshot.sunset else None,
    }
