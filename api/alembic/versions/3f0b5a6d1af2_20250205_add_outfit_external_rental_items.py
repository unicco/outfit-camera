"""Add outfit_external_rental_items link table.

Revision ID: 3f0b5a6d1af2
Revises: ru3mdni0s7ua
Create Date: 2025-02-05 14:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f0b5a6d1af2"
down_revision: Union[str, None] = "ru3mdni0s7ua"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outfit_external_rental_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("outfit_record_id", sa.String(length=36), nullable=False),
        sa.Column("external_rental_item_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["external_rental_item_id"],
            ["external_rental_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outfit_record_id"], ["outfit_records.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "outfit_record_id",
            "external_rental_item_id",
            name="uq_outfit_external_rental",
        ),
    )
    op.create_index(
        "idx_outfit_external_rental_record",
        "outfit_external_rental_items",
        ["outfit_record_id"],
    )
    op.create_index(
        "idx_outfit_external_rental_item",
        "outfit_external_rental_items",
        ["external_rental_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_outfit_external_rental_item",
        table_name="outfit_external_rental_items",
    )
    op.drop_index(
        "idx_outfit_external_rental_record",
        table_name="outfit_external_rental_items",
    )
    op.drop_table("outfit_external_rental_items")
