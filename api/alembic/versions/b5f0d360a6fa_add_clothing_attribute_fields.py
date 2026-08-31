"""Add clothing attribute fields.

Revision ID: b5f0d360a6fa
Revises: 0001_initial
Create Date: 2025-10-04 10:41:30.668632

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5f0d360a6fa"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add new attribute columns to the clothing_items table."""
    op.add_column(
        "clothing_items",
        sa.Column("silhouette_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "clothing_items",
        sa.Column("silhouette_features", sa.JSON(), nullable=True),
    )
    op.add_column(
        "clothing_items",
        sa.Column("sleeve_length", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "clothing_items",
        sa.Column("neckline_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "clothing_items",
        sa.Column("attributes_metadata", sa.JSON(), nullable=True),
    )
    op.add_column(
        "clothing_items",
        sa.Column("pattern_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "clothing_items",
        sa.Column("design_complexity", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "clothing_items",
        sa.Column("color_harmony_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Remove the attribute columns from the clothing_items table."""
    op.drop_column("clothing_items", "color_harmony_score")
    op.drop_column("clothing_items", "design_complexity")
    op.drop_column("clothing_items", "pattern_type")
    op.drop_column("clothing_items", "attributes_metadata")
    op.drop_column("clothing_items", "neckline_type")
    op.drop_column("clothing_items", "sleeve_length")
    op.drop_column("clothing_items", "silhouette_features")
    op.drop_column("clothing_items", "silhouette_type")
