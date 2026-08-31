"""Add rental_cost to external_rental_items.

コスパ計算を「月額固定 ÷ 累計着用回数」から「アイテム単位の料金 ÷ 着用回数」へ
変更するため、各レンタルアイテムに編集可能な料金フィールドを追加する。
既存行はデフォルトの月額 ¥5,940 で埋める。

Revision ID: f2a9c7b41e63
Revises: b3f7c2a9e1d4
Create Date: 2026-07-03 10:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a9c7b41e63"
down_revision: Union[str, None] = "b3f7c2a9e1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "external_rental_items",
        sa.Column(
            "rental_cost",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="9999",
        ),
    )


def downgrade() -> None:
    op.drop_column("external_rental_items", "rental_cost")
