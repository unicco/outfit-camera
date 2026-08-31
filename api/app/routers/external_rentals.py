"""API endpoints for external rental integrations."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import AuthenticatedActor, require_external_rental_auth
from ..database import get_db
from ..schemas.external_rentals import (
    ExampleRentalImportRequest,
    ExampleRentalImportResponse,
    ExampleRentalRentalRecord,
    ExternalRentalItemResponse,
    ExternalRentalSummaryResponse,
    ExternalRentalUpdateRequest,
)
from ..services.external_rental_service import ExternalRentalService
from ..security import require_authenticated_request

router = APIRouter(
    prefix="/api/v2/external-rentals",
    tags=["external-rentals"],
    dependencies=[Depends(require_authenticated_request)],
)

logger = logging.getLogger(__name__)


@router.post(
    "/example_rental/import",
    response_model=ExampleRentalImportResponse,
    status_code=status.HTTP_200_OK,
)
def import_example_rental_rentals(
    payload: ExampleRentalImportRequest,
    actor: AuthenticatedActor = Depends(require_external_rental_auth),
    db: Session = Depends(get_db),
) -> ExampleRentalImportResponse:
    """Upsert example_rental rental items scraped by Chrome extension."""
    logger.info(
        "Processing example_rental import (%d items) requested by %s via %s",
        len(payload.items),
        actor.identifier or "unknown",
        actor.source,
    )
    service = ExternalRentalService(db)

    records: list[ExampleRentalRentalRecord] = []
    for item in payload.items:
        records.append(
            ExampleRentalRentalRecord(
                name=item.item_name,
                brand=item.brand,
                size=item.size,
                management_number=item.management_number,
                return_due_date=item.return_due_date,
                raw_attributes=item.raw_attributes,
                image_url=item.image_url,
            )
        )

    try:
        result = service.import_example_rental_items(
            records, captured_at=payload.captured_at
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    summary = service.get_example_rental_summary()
    items = [
        ExternalRentalItemResponse.model_validate(service.build_item_view(item))
        for item in summary.items
    ]

    return ExampleRentalImportResponse(
        created_count=len(result.created),
        updated_count=len(result.updated),
        returned_count=len(result.returned),
        total_active_items=summary.active_item_count,
        items=items,
    )


@router.get("/summary", response_model=ExternalRentalSummaryResponse)
def get_external_rental_summary(
    actor: AuthenticatedActor = Depends(require_external_rental_auth),
    db: Session = Depends(get_db),
) -> ExternalRentalSummaryResponse:
    """Return aggregated rental metrics for dashboard."""
    logger.info(
        "Fetching external rental summary requested by %s via %s",
        actor.identifier or "unknown",
        actor.source,
    )
    service = ExternalRentalService(db)
    summary = service.get_example_rental_summary()
    items = [
        ExternalRentalItemResponse.model_validate(service.build_item_view(item))
        for item in summary.items
    ]
    returned_items = [
        ExternalRentalItemResponse.model_validate(service.build_item_view(item))
        for item in summary.returned_items
    ]

    cost_per_wear: Optional[float] = (
        float(summary.cost_per_wear) if summary.cost_per_wear is not None else None
    )

    return ExternalRentalSummaryResponse(
        plan_cost=float(summary.plan_cost),
        total_wear_count=summary.total_wear_count,
        cost_per_wear=cost_per_wear,
        active_item_count=summary.active_item_count,
        items=items,
        returned_items=returned_items,
    )


@router.patch(
    "/{item_id}",
    response_model=ExternalRentalItemResponse,
)
def update_external_rental_item(
    item_id: str,
    payload: ExternalRentalUpdateRequest,
    actor: AuthenticatedActor = Depends(require_external_rental_auth),
    db: Session = Depends(get_db),
) -> ExternalRentalItemResponse:
    """Update wear count, due date, or status for a rental item."""
    logger.info(
        "Updating external rental item %s requested by %s via %s",
        item_id,
        actor.identifier or "unknown",
        actor.source,
    )
    if (
        payload.wear_count is None
        and payload.increment_wear is None
        and payload.last_worn_at is None
        and payload.return_due_date is None
        and payload.status is None
        and payload.notes is None
        and payload.rental_cost is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No updatable fields provided",
        )

    if payload.wear_count is not None and payload.increment_wear is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Specify either wearCount or incrementWear, not both",
        )

    service = ExternalRentalService(db)
    try:
        item = service.update_item(
            item_id,
            wear_count=payload.wear_count,
            increment_wear=payload.increment_wear,
            last_worn_at=payload.last_worn_at,
            return_due_date=payload.return_due_date,
            status=payload.status,
            notes=payload.notes,
            rental_cost=payload.rental_cost,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    response_item = ExternalRentalItemResponse.model_validate(
        service.build_item_view(item)
    )
    return response_item
