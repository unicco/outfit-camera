"""Drop morning dashboard state table.

Revision ID: 7c4e1b0a2d35
Revises: 2e4b1a3c5d6e
Create Date: 2025-03-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7c4e1b0a2d35"
down_revision: Union[str, Sequence[str], None] = "3f0b5a6d1af2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "daystate_morning_dashboard"
INDEX_NAME = "idx_morning_dashboard_expire_at"


def upgrade() -> None:
    """Drop the obsolete morning dashboard state table."""
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{TABLE_NAME}" CASCADE'))


def downgrade() -> None:
    """Recreate the morning dashboard state table."""
    op.create_table(
        TABLE_NAME,
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column(
            "should_show_dashboard",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(INDEX_NAME, TABLE_NAME, ["expire_at"])
