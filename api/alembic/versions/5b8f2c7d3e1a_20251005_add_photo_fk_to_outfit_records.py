"""Add foreign key and relationship for outfit record photos.

Revision ID: 5b8f2c7d3e1a
Revises: b5f0d360a6fa
Create Date: 2025-10-05 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5b8f2c7d3e1a"
down_revision: Union[str, Sequence[str], None] = "b5f0d360a6fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FK_NAME = "fk_outfit_records_photo_id"


def _cleanup_orphan_outfit_records() -> None:
    """Remove outfit records that reference missing photos before adding FK."""
    bind = op.get_bind()
    orphan_rows = bind.execute(sa.text("""
            SELECT id
            FROM outfit_records
            WHERE photo_id IS NULL
               OR photo_id = ''
               OR NOT EXISTS (
                    SELECT 1
                    FROM photos p
                    WHERE p.id = outfit_records.photo_id
               )
            """)).fetchall()

    if not orphan_rows:
        return

    orphan_ids = [row[0] for row in orphan_rows]

    # Delete child records first to maintain referential integrity
    outfit_items = sa.table(
        "outfit_items", sa.column("outfit_record_id", sa.String(length=36))
    )
    bind.execute(
        outfit_items.delete().where(outfit_items.c.outfit_record_id.in_(orphan_ids))
    )

    outfit_records = sa.table("outfit_records", sa.column("id", sa.String(length=36)))
    bind.execute(outfit_records.delete().where(outfit_records.c.id.in_(orphan_ids)))


def upgrade() -> None:
    """Add foreign key constraint and tighten photo_id length."""
    _cleanup_orphan_outfit_records()

    with op.batch_alter_table("outfit_records", schema=None) as batch_op:
        batch_op.alter_column(
            "photo_id",
            existing_type=sa.String(length=255),
            type_=sa.String(length=36),
            existing_nullable=False,
        )

    op.create_foreign_key(
        FK_NAME,
        "outfit_records",
        "photos",
        ["photo_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Revert foreign key constraint and column length."""
    op.drop_constraint(FK_NAME, "outfit_records", type_="foreignkey")

    with op.batch_alter_table("outfit_records", schema=None) as batch_op:
        batch_op.alter_column(
            "photo_id",
            existing_type=sa.String(length=36),
            type_=sa.String(length=255),
            existing_nullable=False,
        )
