"""Allow null photo_id on outfit records for manual entries.

Revision ID: 3d5a79c2f4b0
Revises: 5b8f2c7d3e1a
Create Date: 2025-10-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "3d5a79c2f4b0"
down_revision: Union[str, Sequence[str], None] = "5b8f2c7d3e1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow NULL photo_id values on outfit_records."""
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE outfit_records SET photo_id = NULL WHERE photo_id = ''")
    )

    with op.batch_alter_table("outfit_records", schema=None) as batch_op:
        batch_op.alter_column(
            "photo_id",
            existing_type=sa.String(length=36),
            existing_nullable=False,
            nullable=True,
        )


def downgrade() -> None:
    """Revert photo_id column to NOT NULL and restore empty strings."""
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE outfit_records SET photo_id = '' WHERE photo_id IS NULL")
    )

    with op.batch_alter_table("outfit_records", schema=None) as batch_op:
        batch_op.alter_column(
            "photo_id",
            existing_type=sa.String(length=36),
            existing_nullable=True,
            nullable=False,
        )
