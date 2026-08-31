"""Add image_url column to external rental items.

Revision ID: ru3mdni0s7ua
Revises: 8f1e6c2a9b40
Create Date: 2025-02-05 09:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ru3mdni0s7ua"
down_revision: Union[str, None] = "8f1e6c2a9b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "external_rental_items",
        sa.Column("image_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("external_rental_items", "image_url")
