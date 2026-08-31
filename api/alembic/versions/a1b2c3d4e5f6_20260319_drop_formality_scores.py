"""Drop formality_scores column from clothing_items.

Revision ID: a1b2c3d4e5f6
Revises: 7c4e1b0a2d35
Create Date: 2026-03-19

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "7c4e1b0a2d35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop formality_scores column from clothing_items."""
    op.drop_column("clothing_items", "formality_scores")


def downgrade() -> None:
    """Re-add formality_scores column to clothing_items."""
    op.add_column(
        "clothing_items",
        sa.Column("formality_scores", sa.JSON(), nullable=True),
    )
