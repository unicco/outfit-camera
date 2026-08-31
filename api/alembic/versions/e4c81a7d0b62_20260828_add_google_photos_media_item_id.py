"""Add google_photos_media_item_id to photos.

コードは以前からこの属性に代入して commit していたが、列が無いので 1 行も
書かれていなかった。列を足して代入を実効化する。

⚠️ 既存行はすべて NULL から始まる。NULL を「未アップロード」と読めるのは
この migration 以降に撮影したぶんだけ。

Revision ID: e4c81a7d0b62
Revises: f2a9c7b41e63
Create Date: 2026-08-28 23:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4c81a7d0b62"
down_revision: Union[str, None] = "f2a9c7b41e63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column("google_photos_media_item_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("photos", "google_photos_media_item_id")
