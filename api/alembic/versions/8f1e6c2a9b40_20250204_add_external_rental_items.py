"""Create external_rental_items table for example_rental integration.

Revision ID: 8f1e6c2a9b40
Revises: d861f2b139ad
Create Date: 2025-02-04 09:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "8f1e6c2a9b40"
down_revision = "d861f2b139ad"
branch_labels = None
depends_on = None


# Column enum definitions reused below (type creation handled separately)
EXTERNAL_SOURCE_ENUM = postgresql.ENUM(
    "EXAMPLE_RENTAL",
    name="externalrentalsource",
    create_type=False,
)
EXTERNAL_STATUS_ENUM = postgresql.ENUM(
    "ACTIVE",
    "RETURNED",
    name="externalrentalstatus",
    create_type=False,
)


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'externalrentalsource') THEN
                CREATE TYPE externalrentalsource AS ENUM ('EXAMPLE_RENTAL');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'externalrentalstatus') THEN
                CREATE TYPE externalrentalstatus AS ENUM ('ACTIVE', 'RETURNED');
            END IF;
        END$$;
        """)

    op.create_table(
        "external_rental_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", EXTERNAL_SOURCE_ENUM, nullable=False),
        sa.Column("source_item_id", sa.String(length=160), nullable=False),
        sa.Column("reference_number", sa.String(length=160), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("size", sa.String(length=80), nullable=True),
        sa.Column("return_due_date", sa.Date(), nullable=True),
        sa.Column(
            "status", EXTERNAL_STATUS_ENUM, nullable=False, server_default="ACTIVE"
        ),
        sa.Column("wear_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_worn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_item_id", name="uq_external_rentals_source_item_id"
        ),
    )

    op.create_index(
        "idx_external_rentals_source_status",
        "external_rental_items",
        ["source", "status"],
    )
    op.create_index(
        "idx_external_rentals_due_date",
        "external_rental_items",
        ["return_due_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_external_rentals_due_date", table_name="external_rental_items")
    op.drop_index(
        "idx_external_rentals_source_status", table_name="external_rental_items"
    )
    op.drop_table("external_rental_items")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'external_rentalstatus') THEN
                DROP TYPE external_rentalstatus;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'externalrentalsource') THEN
                DROP TYPE externalrentalsource;
            END IF;
        END$$;
        """)
