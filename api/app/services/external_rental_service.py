"""Service layer for external rental integrations."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence

from sqlalchemy import case
from sqlalchemy.orm import Session

from ..constants.external_rentals import EXAMPLE_RENTAL_MONTHLY_PLAN_JPY
from ..external_rental_models import (
    ExternalRentalItem,
    ExternalRentalSource,
    ExternalRentalStatus,
)
from ..schemas.external_rentals import ExampleRentalRentalRecord
from ..utils.timezone_utils import TimezoneUtils, jst_now


@dataclass(slots=True)
class ImportResult:
    """Result summary for rental imports."""

    created: list[ExternalRentalItem]
    updated: list[ExternalRentalItem]
    returned: list[ExternalRentalItem]


@dataclass(slots=True)
class SummaryResult:
    """Aggregated metrics for UI rendering."""

    items: list[ExternalRentalItem]
    returned_items: list[ExternalRentalItem]
    plan_cost: Decimal
    total_cost: Decimal
    total_wear_count: int
    active_item_count: int

    @property
    def cost_per_wear(self) -> Optional[Decimal]:
        if self.total_wear_count <= 0:
            return None
        return (self.total_cost / Decimal(self.total_wear_count)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


class ExternalRentalService:
    """外部レンタル連携のビジネスロジックを提供するサービス."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- example_rental import -------------------------------------------------

    def import_example_rental_items(
        self,
        records: Sequence[ExampleRentalRentalRecord],
        captured_at: Optional[datetime] = None,
    ) -> ImportResult:
        """Upsert items scraped from example_rental."""
        if not records:
            return ImportResult(created=[], updated=[], returned=[])

        captured_at = captured_at or jst_now()
        captured_at = TimezoneUtils.validate_timezone_aware(captured_at)

        existing_items = (
            self.db.query(ExternalRentalItem)
            .filter(ExternalRentalItem.source == ExternalRentalSource.EXAMPLE_RENTAL)
            .all()
        )
        existing_by_id = {item.source_item_id: item for item in existing_items}

        seen_source_ids: set[str] = set()
        created: list[ExternalRentalItem] = []
        updated: list[ExternalRentalItem] = []

        for record in records:
            source_item_id = self._make_source_item_id(record)
            seen_source_ids.add(source_item_id)

            return_due_date = self._parse_return_due_date(record.return_due_date)
            reference_number = self._normalize_reference(record.management_number)
            raw_payload = dict(record.raw_attributes) if record.raw_attributes else {}
            if record.image_url:
                raw_payload.setdefault("image_url", record.image_url)

            existing = existing_by_id.get(source_item_id)
            if existing:
                existing.update_from_payload(
                    name=record.name,
                    brand=record.brand,
                    size=record.size,
                    return_due_date=return_due_date,
                    reference_number=reference_number,
                    captured_at=captured_at,
                    raw_payload=raw_payload,
                    image_url=record.image_url,
                )
                updated.append(existing)
            else:
                item = ExternalRentalItem(
                    source=ExternalRentalSource.EXAMPLE_RENTAL,
                    source_item_id=source_item_id,
                    reference_number=reference_number,
                    name=record.name,
                    brand=record.brand,
                    size=record.size,
                    return_due_date=return_due_date,
                    captured_at=captured_at,
                    raw_payload=raw_payload,
                    status=ExternalRentalStatus.ACTIVE,
                    image_url=record.image_url,
                )
                self.db.add(item)
                created.append(item)

        returned: list[ExternalRentalItem] = []
        for item in existing_items:
            if (
                item.source_item_id not in seen_source_ids
                and item.status == ExternalRentalStatus.ACTIVE
            ):
                item.mark_returned()
                returned.append(item)

        self.db.commit()

        for obj in created + updated + returned:
            self.db.refresh(obj)

        return ImportResult(created=created, updated=updated, returned=returned)

    # --- updates ----------------------------------------------------------------

    def update_item(
        self,
        item_id: str,
        *,
        wear_count: Optional[int] = None,
        increment_wear: Optional[int] = None,
        last_worn_at: Optional[datetime] = None,
        return_due_date: Optional[str | date] = None,
        status: Optional[ExternalRentalStatus] = None,
        notes: Optional[str] = None,
        rental_cost: Optional[float] = None,
    ) -> Optional[ExternalRentalItem]:
        """Apply partial updates to an item."""
        item = (
            self.db.query(ExternalRentalItem)
            .filter(ExternalRentalItem.id == item_id)
            .first()
        )
        if not item:
            return None

        if increment_wear is not None:
            item.wear_count = max(0, (item.wear_count or 0) + increment_wear)
        elif wear_count is not None:
            item.wear_count = max(0, wear_count)

        if last_worn_at is not None:
            item.last_worn_at = TimezoneUtils.validate_timezone_aware(last_worn_at)
        elif increment_wear and increment_wear > 0 and item.last_worn_at is None:
            item.last_worn_at = jst_now()

        if return_due_date is not None:
            item.return_due_date = self._parse_return_due_date(return_due_date)

        if status is not None and status != item.status:
            item.status = status
            if status == ExternalRentalStatus.RETURNED:
                item.returned_at = item.returned_at or jst_now()
            else:
                item.returned_at = None

        if notes is not None:
            item.notes = notes

        if rental_cost is not None:
            item.rental_cost = Decimal(str(rental_cost))

        self.db.commit()
        self.db.refresh(item)
        return item

    # --- summary ----------------------------------------------------------------

    def get_example_rental_summary(self) -> SummaryResult:
        """Aggregate active example_rental items."""
        plan_cost = EXAMPLE_RENTAL_MONTHLY_PLAN_JPY

        items = (
            self.db.query(ExternalRentalItem)
            .filter(
                ExternalRentalItem.source == ExternalRentalSource.EXAMPLE_RENTAL,
                ExternalRentalItem.status == ExternalRentalStatus.ACTIVE,
            )
            .order_by(
                case(
                    (ExternalRentalItem.return_due_date.is_(None), 1),
                    else_=0,
                ),
                ExternalRentalItem.return_due_date.asc(),
                ExternalRentalItem.name.asc(),
            )
            .all()
        )

        returned_items = (
            self.db.query(ExternalRentalItem)
            .filter(
                ExternalRentalItem.source == ExternalRentalSource.EXAMPLE_RENTAL,
                ExternalRentalItem.status == ExternalRentalStatus.RETURNED,
            )
            .order_by(
                ExternalRentalItem.returned_at.desc().nullslast(),
                ExternalRentalItem.captured_at.desc().nullslast(),
                ExternalRentalItem.name.asc(),
            )
            .limit(50)
            .all()
        )

        total_wear = sum((item.wear_count or 0) for item in items + returned_items)
        total_cost = sum(
            (Decimal(item.rental_cost) for item in items + returned_items),
            Decimal("0"),
        )

        return SummaryResult(
            items=items,
            returned_items=returned_items,
            plan_cost=plan_cost,
            total_cost=total_cost,
            total_wear_count=total_wear,
            active_item_count=len(items),
        )

    # --- serialization helpers --------------------------------------------------

    def build_item_view(self, item: ExternalRentalItem) -> dict[str, object]:
        """Serialize an item for API responses with derived metrics."""
        today = TimezoneUtils.now_jst().date()
        days_until_due: Optional[int] = None
        if item.return_due_date:
            days_until_due = (item.return_due_date - today).days

        # コスパはアイテム単位: そのアイテムの料金 ÷ そのアイテムの着用回数。
        wear_count = item.wear_count or 0
        per_wear_cost: Optional[float] = None
        if wear_count > 0:
            per_wear_cost = float(
                (Decimal(item.rental_cost) / Decimal(wear_count)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )

        return {
            "id": item.id,
            "source": item.source.value,
            "name": item.name,
            "brand": item.brand,
            "size": item.size,
            "management_number": item.reference_number or item.source_item_id,
            "return_due_date": item.return_due_date,
            "status": item.status,
            "wear_count": item.wear_count or 0,
            "last_worn_at": item.last_worn_at,
            "captured_at": item.captured_at,
            "returned_at": item.returned_at,
            "days_until_due": days_until_due,
            "rental_cost": float(item.rental_cost),
            "cost_per_wear": per_wear_cost,
            "image_url": item.image_url,
        }

    # --- internal helpers -------------------------------------------------------

    @staticmethod
    def _make_source_item_id(record: ExampleRentalRentalRecord) -> str:
        """Build stable unique identifier for an imported item."""
        if record.management_number:
            base = record.management_number
        else:
            parts = [record.brand or "", record.name]
            base = "|".join(part.strip() for part in parts if part and part.strip())
            if not base:
                raise ValueError(
                    "example_rental item requires managementNumber or recognizable fields"
                )

        cleaned = re.sub(r"[^0-9A-Za-z]+", "", base.upper())
        if cleaned:
            return cleaned

        # As a final fallback, use a deterministic namespace uuid
        return uuid.uuid5(uuid.NAMESPACE_DNS, base).hex

    @staticmethod
    def _normalize_reference(reference: Optional[str]) -> Optional[str]:
        if reference is None:
            return None
        trimmed = reference.strip()
        return trimmed or None

    @staticmethod
    def _parse_return_due_date(
        value: Optional[str | date],
    ) -> Optional[date]:
        if value is None:
            return None

        if isinstance(value, date) and not isinstance(value, datetime):
            return value

        if isinstance(value, datetime):
            return TimezoneUtils.to_jst(value).date()

        text = value.strip()
        if not text:
            return None

        normalized = (
            text.replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
            .replace("/", "-")
            .replace(".", "-")
        )
        normalized = re.sub(
            r"[()\u3000\s]", "", normalized
        )  # Remove spaces & parentheses

        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                return parsed.date()
            except ValueError:
                continue

        digits = re.findall(r"\d+", text)
        if len(digits) >= 3:
            year, month, day = map(int, digits[:3])
            return date(year, month, day)

        raise ValueError(f"Unsupported date format: {value}")
