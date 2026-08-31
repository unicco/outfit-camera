"""Add attendees column to photos.

撮影日に会った人（カレンダー `@名前` 由来）を保持し、「前回その人と会った時の
コーデ」を引けるようにする。過去バックフィルはせず、
デプロイ以降に撮影したぶんだけ記録する。

Revision ID: b3f7c2a9e1d4
Revises: c7a2e1f04b9d
Create Date: 2026-06-18 18:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f7c2a9e1d4"
down_revision: Union[str, None] = "c7a2e1f04b9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column("attendees", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("photos", "attendees")
