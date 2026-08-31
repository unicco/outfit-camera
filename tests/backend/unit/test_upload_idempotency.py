"""同じ photo_id を 2 度受けても 1 レコードのままであること.

以前は `_1` `_2` と suffix を付けた別レコードを作っていた。Pi の再送は
送信前に存在確認を通すが、確認と送信の間に UI（別プロセス）が同じ写真を上げると
ロックでは塞げず、1 日に 2 レコードできる。ここで固定するのは「API 側が
photo_id で冪等」という性質そのもので、これが壊れると再送の安全性が消える。

`app.routers.upload` は cv2 を transitively import するため、libGL の無い最小環境では
import できない。`test_upload_attendees_background.py` と同じ skipif ゲートを置く。
⚠️ **このリポの CI では発火しない**（`requirements-api.txt` の opencv-python が入るので
6 件とも実行される。PR #1792 の Test Suite で実測）。ゲートは手元の最小環境向けで、
「CI では検証されていない」を意味しない。
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Photo

CAMERA_FILENAME = "photo_20260808_112459.jpg"
CAMERA_PHOTO_ID = "photo_20260808_112459"


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
    """GCS の代わり。何回・どの photo_id で保存されたかを記録する."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def upload_photo(self, contents: bytes, photo_id: str) -> dict[str, str]:
        self.calls.append(photo_id)
        return {"url": f"https://storage.example/{photo_id}.jpg"}


class _FakeThreadPool:
    """AI 検出・Google Photos・参加者記録の submit を記録するだけで実行しない."""

    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        self.submitted.append(getattr(fn, "__name__", repr(fn)))

        class _Future:
            def add_done_callback(self, callback: Any) -> None:
                return None

        return _Future()


@pytest.fixture
def db():
    """本物の一意制約が要る。PK 衝突をモックで再現すると窓の検証にならない."""
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


def _upload_file(filename: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(_jpeg_bytes()), filename=filename)


async def _upload(db, filename: str = CAMERA_FILENAME) -> dict[str, Any]:
    """関数を直に呼ぶ。Form(...) の既定値は解決されないので全部明示する."""
    from app.routers import upload

    return await upload.upload_photo(
        file=_upload_file(filename),
        original_filename=None,
        captured_date=None,
        source=None,
        db=db,
    )


def _photo_rows(db, photo_id_prefix: str) -> list[Photo]:
    """suffix 付き（`photo_..._1`）が増えていないかを見るので前方一致で数える."""
    return db.query(Photo).filter(Photo.id.like(f"{photo_id_prefix}%")).all()


@pytest.mark.asyncio
async def test_same_photo_id_twice_keeps_one_record(db, upload_service, thread_pool):
    first = await _upload(db)
    second = await _upload(db)

    assert first["photo_id"] == CAMERA_PHOTO_ID
    assert first.get("duplicate") is None
    # suffix 付きの別 ID になっていない＝Pi と UI が同じレコードを指す
    assert second["photo_id"] == CAMERA_PHOTO_ID
    assert second["duplicate"] is True
    assert second["deleted"] is False
    assert len(_photo_rows(db, CAMERA_PHOTO_ID)) == 1


@pytest.mark.asyncio
async def test_duplicate_skips_storage_and_background_work(
    db, upload_service, thread_pool
):
    await _upload(db)
    submitted_after_first = list(thread_pool.submitted)

    await _upload(db)

    # 2 回目で GCS に書き直さない・AI 検出と Google Photos を再実行しない
    assert upload_service.calls == [CAMERA_PHOTO_ID]
    assert thread_pool.submitted == submitted_after_first


@pytest.mark.asyncio
async def test_deleted_photo_is_not_resurrected(db, upload_service, thread_pool):
    await _upload(db)
    db.query(Photo).filter(Photo.id == CAMERA_PHOTO_ID).update(
        {"deleted_at": datetime(2026, 8, 8, 20, 0)}
    )
    db.commit()

    response = await _upload(db)

    assert response["duplicate"] is True
    assert response["deleted"] is True
    assert len(_photo_rows(db, CAMERA_PHOTO_ID)) == 1
    # 消した写真が別 ID で蘇らない
    assert db.query(Photo).filter(Photo.id == CAMERA_PHOTO_ID).one().deleted_at
    # 冒頭の lookup で返す（削除済を見ない lookup だと INSERT まで進み、PK 衝突で
    # 拾う前に GCS へ書いてしまう）
    assert upload_service.calls == [CAMERA_PHOTO_ID]


@pytest.mark.asyncio
async def test_insert_race_returns_the_existing_record(
    db, upload_service, thread_pool, monkeypatch
):
    """存在確認と INSERT の間に別経路が入っても重複を作らない.

    冒頭の lookup を 1 度だけ「無い」と見せかけて窓を再現する。DB の一意制約が
    最後の砦になっていないと、ここで 409 か 2 レコードのどちらかになる。
    """
    from app.api_shared import PhotoRepository

    await _upload(db)

    real_lookup = PhotoRepository.get_by_id_including_deleted
    calls = {"n": 0}

    def lookup_once_blind(self, photo_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_lookup(self, photo_id)

    monkeypatch.setattr(
        PhotoRepository, "get_by_id_including_deleted", lookup_once_blind
    )

    response = await _upload(db)

    assert response["duplicate"] is True
    assert response["photo_id"] == CAMERA_PHOTO_ID
    assert len(_photo_rows(db, CAMERA_PHOTO_ID)) == 1


@pytest.mark.asyncio
async def test_non_camera_filename_still_creates_separate_records(
    db, upload_service, thread_pool
):
    # 手元の写真を手動で上げる経路。ファイル名は同じでも別の写真なので UUID を振る
    first = await _upload(db, filename="IMG_1234.jpg")
    second = await _upload(db, filename="IMG_1234.jpg")

    assert first["photo_id"] != second["photo_id"]
    assert second.get("duplicate") is None
    assert db.query(Photo).count() == 2


@pytest.mark.asyncio
async def test_database_error_rolls_back(db, upload_service, thread_pool, monkeypatch):
    """DB エラーでセッションを汚したまま返さない（旧 test_photo_upload_duplicate_handling から引き取り）."""
    from app.api_shared import PhotoRepository

    def boom(self, **kwargs):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(PhotoRepository, "create", boom)
    rollbacks: list[bool] = []
    monkeypatch.setattr(type(db), "rollback", lambda self: rollbacks.append(True))

    with pytest.raises(HTTPException) as excinfo:
        await _upload(db)

    assert excinfo.value.status_code == 500
    assert rollbacks == [True]
