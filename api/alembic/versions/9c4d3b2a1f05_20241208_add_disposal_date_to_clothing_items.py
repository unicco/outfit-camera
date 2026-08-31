"""Add disposal_date column to clothing_items.

Revision ID: 9c4d3b2a1f05
Revises: 3d5a79c2f4b0
Create Date: 2024-12-08 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "9c4d3b2a1f05"
down_revision: Union[str, None] = "2e4b1a3c5d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "clothing_items"
COLUMN_NAME = "disposal_date"
INDEX_NAME = "idx_clothing_disposal_date"
SCHEMA_NAME = "public"


def _column_exists(bind: Connection) -> bool:
    result = bind.execute(
        sa.text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table
              AND column_name = :column
            LIMIT 1
            """),
        {"schema": SCHEMA_NAME, "table": TABLE_NAME, "column": COLUMN_NAME},
    )
    return result.first() is not None


def _index_exists(bind: Connection) -> bool:
    result = bind.execute(
        sa.text("""
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = :schema
              AND tablename = :table
              AND indexname = :index
            LIMIT 1
            """),
        {"schema": SCHEMA_NAME, "table": TABLE_NAME, "index": INDEX_NAME},
    )
    return result.first() is not None


def upgrade() -> None:
    """Safely add disposal_date column and index if missing."""
    bind = op.get_bind()

    if not _column_exists(bind):
        op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.Date(), nullable=True))

    if not _index_exists(bind):
        op.create_index(INDEX_NAME, TABLE_NAME, [COLUMN_NAME], unique=False)


def downgrade() -> None:
    """Drop index and column only when they exist."""
    bind = op.get_bind()

    if _index_exists(bind):
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)

    if _column_exists(bind):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
