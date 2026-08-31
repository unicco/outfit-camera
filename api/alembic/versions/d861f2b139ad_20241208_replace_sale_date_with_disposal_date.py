"""Migrate sale_date to disposal_date and drop sale_date column.

Revision ID: d861f2b139ad
Revises: 9c4d3b2a1f05
Create Date: 2024-12-08 00:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision: str = "d861f2b139ad"
down_revision: Union[str, None] = "9c4d3b2a1f05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "clothing_items"
SALE_COLUMN = "sale_date"
DISPOSAL_COLUMN = "disposal_date"


def _column_exists(bind: Connection, column_name: str) -> bool:
    result = bind.execute(
        sa.text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """),
        {"table_name": TABLE_NAME, "column_name": column_name},
    )
    return result.first() is not None


def upgrade() -> None:
    """Copy sale dates into disposal_date and drop the sale_date column."""
    bind = op.get_bind()

    has_sale_column = _column_exists(bind, SALE_COLUMN)
    has_disposal_column = _column_exists(bind, DISPOSAL_COLUMN)

    if has_sale_column and has_disposal_column:
        op.execute(sa.text("""
                UPDATE clothing_items
                SET disposal_date = sale_date
                WHERE disposal_date IS NULL
                  AND sale_date IS NOT NULL
                """))

    if has_sale_column:
        op.drop_column(TABLE_NAME, SALE_COLUMN)


def downgrade() -> None:
    """Recreate sale_date and populate it from disposal_date if present."""
    bind = op.get_bind()

    has_sale_column = _column_exists(bind, SALE_COLUMN)
    has_disposal_column = _column_exists(bind, DISPOSAL_COLUMN)

    if not has_sale_column:
        op.add_column(TABLE_NAME, sa.Column(SALE_COLUMN, sa.Date(), nullable=True))

    if has_disposal_column:
        op.execute(sa.text("""
                UPDATE clothing_items
                SET sale_date = disposal_date
                WHERE disposal_date IS NOT NULL
                """))
