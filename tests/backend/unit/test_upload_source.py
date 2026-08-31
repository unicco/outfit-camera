"""写真がどの経路で届いたかを Photo.source に残すこと.

以前は Form の `source` を受け取るシグネチャが無く、タッチスクリーン UI が
送っていた値は捨てられて全件 'upload' で記録されていた。ここで固定するのは
「送り手が名乗った経路がそのまま列に入る」ことと「知らない値でも保存は落ちない」の
2 つ。後者が壊れると、経路のラベルが読めないだけで写真そのものを失う。

`app.routers.upload` の import ゲートは test_upload_idempotency.py と同じ理由。
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Photo

CAMERA_FILENAME = "photo_20260810_143012.jpg"
CAMERA_PHOTO_ID = "photo_20260810_143012"


def _upload_router_importable() -> bool:
    """True when the upload router (and its heavy deps) can be imported."""
    try:
        import app.routers.upload  # noqa: F401

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _upload_router_importable(),
    reason="upload router unavailable (heavy deps such as cv2/libGL missing)",
)


class _FakeUploadService:
    """GCS の代わり。保存の成否だけ成立させる."""

    async def upload_photo(self, contents: bytes, photo_id: str) -> dict[str, str]:
        return {"url": f"https://storage.example/{photo_id}.jpg"}


class _FakeThreadPool:
    """AI 検出・Google Photos・参加者記録を submit しても走らせない."""

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        class _Future:
            def add_done_callback(self, callback: Any) -> None:
                return None

        return _Future()


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


@pytest.fixture
def upload_service(monkeypatch) -> _FakeUploadService:
    service = _FakeUploadService()
    # 関数内 import なので提供元のモジュール側を差し替える
    monkeypatch.setattr(
        "app.image_upload_service.get_image_upload_service", lambda: service
    )
    return service


@pytest.fixture
def thread_pool(monkeypatch) -> _FakeThreadPool:
    from app.routers import upload

    pool = _FakeThreadPool()
    monkeypatch.setattr(upload, "AI_DETECTION_THREAD_POOL", pool)
    monkeypatch.setattr(upload, "DB_AVAILABLE", True)
    return pool


def _jpeg_bytes() -> bytes:
    """cv2.imdecode が通る最小の JPEG."""
    import cv2
    import numpy as np

    image = np.zeros((8, 8, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return bytes(encoded.tobytes())


async def _upload(db, source: str | None) -> dict[str, Any]:
    """関数を直に呼ぶ。Form(...) の既定値は解決されないので全部明示する."""
    from app.routers import upload

    return await upload.upload_photo(
        file=UploadFile(file=io.BytesIO(_jpeg_bytes()), filename=CAMERA_FILENAME),
        original_filename=None,
        captured_date=None,
        source=source,
        db=db,
    )


def _stored_source(db) -> str:
    return str(db.query(Photo).filter(Photo.id == CAMERA_PHOTO_ID).one().source)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["touchscreen", "camera_retry", "upload"])
async def test_known_source_is_recorded(db, upload_service, thread_pool, source):
    """送り手が名乗った経路がそのまま入る（3 経路を DB から区別できる）."""
    await _upload(db, source=source)

    assert _stored_source(db) == source


@pytest.mark.asyncio
async def test_missing_source_falls_back_to_upload(db, upload_service, thread_pool):
    """source を送らない経路（手動アップロード）は 'upload' になる."""
    await _upload(db, source=None)

    assert _stored_source(db) == "upload"


@pytest.mark.asyncio
async def test_unknown_source_is_stored_as_upload(db, upload_service, thread_pool):
    """知らない値でも 400 にせず保存する（写真は撮り直しが効かない）."""
    response = await _upload(db, source="' OR 1=1 --")

    assert response["photo_id"] == CAMERA_PHOTO_ID
    assert _stored_source(db) == "upload"


@pytest.mark.asyncio
async def test_source_is_decided_by_the_first_writer(db, upload_service, thread_pool):
    """同じ写真が別経路から再送されても source は書き換わらない（先勝ち）.

    UI と Pi の再送は同じ写真を上げうる。冪等応答は既存レコードをそのまま返す
    ので、2 回目が名乗った経路は捨てる。
    """
    await _upload(db, source="touchscreen")

    response = await _upload(db, source="camera_retry")

    assert response["duplicate"] is True
    assert _stored_source(db) == "touchscreen"
