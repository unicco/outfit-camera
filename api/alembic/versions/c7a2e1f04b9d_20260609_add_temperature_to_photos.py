"""Add temperature_max / temperature_min columns to photos.

起床ブリーフ画面で「今日の気温に近い過去の記録」を照合するため、
撮影日の設定地点の日次気温（Open-Meteo Archive で backfill）を保持する。

Revision ID: c7a2e1f04b9d
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7a2e1f04b9d"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column("temperature_max", sa.Float(), nullable=True),
    )
    op.add_column(
        "photos",
        sa.Column("temperature_min", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("photos", "temperature_min")
    op.drop_column("photos", "temperature_max")
