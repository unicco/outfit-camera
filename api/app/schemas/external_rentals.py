"""Pydantic schemas for external rental integrations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from pydantic import Field

from ..external_rental_models import ExternalRentalStatus
from .base import BaseModel


class ExampleRentalRentalItemPayload(BaseModel):
    """Payload scraped from example_rental 'レンタル中のアイテム'."""

    brand: Optional[str] = None
    item_name: str
    size: Optional[str] = None
    management_number: Optional[str] = None
    return_due_date: Optional[str | date] = None
    raw_attributes: Optional[dict[str, Any]] = None
    image_url: Optional[str] = None


class ExampleRentalImportRequest(BaseModel):
    """Request body for uploading example_rental rentals."""

    items: list[ExampleRentalRentalItemPayload]
    captured_at: Optional[datetime] = None


class ExternalRentalItemResponse(BaseModel):
    """Serialized rental item info."""

    id: str
    source: str
    name: str
    brand: Optional[str]
    size: Optional[str]
    management_number: Optional[str]
    return_due_date: Optional[date]
    status: ExternalRentalStatus
    wear_count: int
    last_worn_at: Optional[datetime]
    captured_at: Optional[datetime]
    returned_at: Optional[datetime]
    days_until_due: Optional[int]
    rental_cost: Optional[float]
    cost_per_wear: Optional[float]
    image_url: Optional[str]


class ExampleRentalImportResponse(BaseModel):
    """Response payload after importing rental items."""

    created_count: int
    updated_count: int
    returned_count: int
    total_active_items: int
    items: list[ExternalRentalItemResponse]


class ExternalRentalSummaryResponse(BaseModel):
    """Aggregated metrics for UI dashboard."""

    plan_cost: float
    total_wear_count: int
    cost_per_wear: Optional[float]
    active_item_count: int
    items: list[ExternalRentalItemResponse]
    returned_items: list[ExternalRentalItemResponse] = Field(default_factory=list)


class ExternalRentalUpdateRequest(BaseModel):
    """Partial update for an external rental item."""

    wear_count: Optional[int] = None
    increment_wear: Optional[int] = None
    last_worn_at: Optional[datetime] = None
    return_due_date: Optional[str | date] = None
    status: Optional[ExternalRentalStatus] = None
    notes: Optional[str] = None
    rental_cost: Optional[float] = None


@dataclass(slots=True)
class ExampleRentalRentalRecord:
    """Internal DTO for example_rental import."""

    name: str
    brand: Optional[str]
    size: Optional[str]
    management_number: Optional[str]
    return_due_date: Optional[str | date]
    raw_attributes: Optional[dict[str, Any]]
    image_url: Optional[str]
