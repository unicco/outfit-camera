"""`google_photos_media_item_id` が本当に永続化されることを固定する.

SQLAlchemy は列でない属性への代入を許すため、列が無いまま代入して commit しても
例外が出ず、`Saved Google Photos media item ID to database` というログだけが残っていた。
「代入できた」ではなく「読み戻せる」ことを見る。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Photo

PHOTO_ID = "photo_20260828_150125"
MEDIA_ITEM_ID = "APgFomh7BmLKN_DUSm_Qexample"


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_column_exists_on_model() -> None:
    assert "google_photos_media_item_id" in Photo.__table__.columns


def test_media_item_id_survives_commit(session_factory) -> None:
    """別セッションから読み戻せること（列が無いと値が消える）."""
    with session_factory() as db:
        db.add(
            Photo(
                id=PHOTO_ID,
                filename=f"{PHOTO_ID}.jpg",
                file_path=f"/p/{PHOTO_ID}.jpg",
                source="camera",
                captured_at=datetime(2026, 8, 28, 15, 1),
            )
        )
        db.commit()

    with session_factory() as db:
        photo = db.query(Photo).filter(Photo.id == PHOTO_ID).first()
        photo.google_photos_media_item_id = MEDIA_ITEM_ID
        db.commit()

    with session_factory() as db:
        photo = db.query(Photo).filter(Photo.id == PHOTO_ID).first()
        assert photo.google_photos_media_item_id == MEDIA_ITEM_ID


def test_defaults_to_none(session_factory) -> None:
    """未設定は NULL。⚠️ NULL は「未アップロード」ではない（列の追加前の分が全部 NULL）."""
    with session_factory() as db:
        db.add(
            Photo(
                id="photo_20260101_000000",
                filename="x.jpg",
                file_path="/p/x.jpg",
                source="camera",
                captured_at=datetime(2026, 1, 1),
            )
        )
        db.commit()

    with session_factory() as db:
        photo = db.query(Photo).filter(Photo.id == "photo_20260101_000000").first()
        assert photo.google_photos_media_item_id is None
