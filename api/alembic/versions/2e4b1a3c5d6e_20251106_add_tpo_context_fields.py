"""Add TPO context fields and morning dashboard state table.

Revision ID: 2e4b1a3c5d6e
Revises: 5b8f2c7d3e1a
Create Date: 2025-11-06 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2e4b1a3c5d6e"
down_revision: Union[str, Sequence[str], None] = "3d5a79c2f4b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "daystate_morning_dashboard"


def upgrade() -> None:
    """Add TPO context columns and create the morning dashboard state table."""
    op.add_column(
        "clothing_items",
        sa.Column("formality_scores", sa.JSON(), nullable=True),
    )
    op.add_column(
        "clothing_items",
        sa.Column("season_suitability", sa.JSON(), nullable=True),
    )
    op.add_column(
        "clothing_items",
        sa.Column("weather_suitability", sa.JSON(), nullable=True),
    )

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

    op.create_index(
        "idx_morning_dashboard_expire_at",
        TABLE_NAME,
        ["expire_at"],
    )


def downgrade() -> None:
    """Drop the dashboard table and remove the added TPO context columns."""
    op.drop_index("idx_morning_dashboard_expire_at", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)

    op.drop_column("clothing_items", "weather_suitability")
    op.drop_column("clothing_items", "season_suitability")
    op.drop_column("clothing_items", "formality_scores")
