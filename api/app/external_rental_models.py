"""Database models for external rental integrations."""

import enum
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)

from .constants.external_rentals import EXAMPLE_RENTAL_MONTHLY_PLAN_JPY
from .models import Base
from .utils.timezone_utils import jst_now


class ExternalRentalSource(str, enum.Enum):
    """外部レンタル連携のソース識別子."""

    EXAMPLE_RENTAL = "EXAMPLE_RENTAL"


class ExternalRentalStatus(str, enum.Enum):
    """レンタルアイテムの状態."""

    ACTIVE = "ACTIVE"
    RETURNED = "RETURNED"


class ExternalRentalItem(Base):
    """外部サービスから取り込んだレンタル中アイテム."""

    __tablename__ = "external_rental_items"
    __table_args__ = (
        Index("idx_external_rentals_source_status", "source", "status"),
        Index("idx_external_rentals_due_date", "return_due_date"),
        Index(
            "uq_external_rentals_source_item_id",
            "source_item_id",
            unique=True,
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Column[ExternalRentalSource] = Column(
        Enum(ExternalRentalSource, name="externalrentalsource", length=40),
        nullable=False,
        index=True,
    )
    source_item_id = Column(String(160), nullable=False, unique=True)
    reference_number = Column(String(160), nullable=True)

    name = Column(String(255), nullable=False)
    brand = Column(String(255), nullable=True)
    size = Column(String(80), nullable=True)

    return_due_date = Column(Date, nullable=True)
    status: Column[ExternalRentalStatus] = Column(
        Enum(ExternalRentalStatus, name="externalrentalstatus", length=40),
        nullable=False,
        default=ExternalRentalStatus.ACTIVE,
    )
    wear_count = Column(Integer, nullable=False, default=0)
    # コスパ計算の分子。デフォルトは月額プラン ¥5,940。キャンペーンや上位プランで
    # 1 か月に複数枚借りた場合は、ユーザーが各アイテムに按分額を入力して調整する。
    rental_cost = Column(
        Numeric(10, 2),
        nullable=False,
        default=lambda: EXAMPLE_RENTAL_MONTHLY_PLAN_JPY,
        server_default="9999",
    )
    last_worn_at = Column(DateTime(timezone=True), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=True)
    returned_at = Column(DateTime(timezone=True), nullable=True)
    image_url = Column(String(500), nullable=True)

    raw_payload = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=jst_now)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=jst_now, onupdate=jst_now
    )

    def mark_returned(self, returned_at: Optional[datetime] = None) -> None:
        """Mark the rental item as returned."""
        self.status = ExternalRentalStatus.RETURNED
        self.returned_at = returned_at or jst_now()

    def update_from_payload(
        self,
        *,
        name: str,
        brand: Optional[str],
        size: Optional[str],
        return_due_date: Optional[date],
        reference_number: Optional[str],
        captured_at: Optional[datetime],
        raw_payload: Optional[dict[str, Any]],
        image_url: Optional[str],
    ) -> None:
        """Apply latest payload data from integration."""
        self.name = name
        self.brand = brand
        self.size = size
        self.return_due_date = return_due_date
        self.reference_number = reference_number
        self.captured_at = captured_at
        self.raw_payload = raw_payload
        self.status = ExternalRentalStatus.ACTIVE
        if image_url is not None:
            self.image_url = image_url
        self.image_url = (raw_payload or {}).get("image_url", self.image_url)


__all__ = [
    "ExternalRentalItem",
    "ExternalRentalSource",
    "ExternalRentalStatus",
]
