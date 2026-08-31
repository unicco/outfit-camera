"""アップロード後に参加者を後追いで記録する経路のテスト.

ICS 取得は 1 本あたり数秒かかるため、`photos.attendees` の記録はアップロード応答の
クリティカルパスから外してバックグラウンドで実行する。同期 await を消した以上、
「submit し忘れ」「UPDATE 対象の ID ずれ」を検出するものが他に無くなるので、
`record_attendees_background` の書き込みをここで固定する。

`app.routers.upload` は cv2 を transitively import するため、headless CI
（libGL 不在）では import できない。`test_write_access_auth.py` と同じ理由で
skipif ゲートを置き、フル依存の環境でだけ走らせる。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, Photo


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


@pytest.fixture
def session_factory(monkeypatch):
    """In-memory DB を `record_attendees_background` の書き込み先に差し替える."""
    from app.routers import upload

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    # SessionLocal は関数内 import なので app.database 側を差し替える。
    # DB_AVAILABLE / Photo は最小 CI 環境で False/None になりうるため明示する。
    monkeypatch.setattr("app.database.SessionLocal", factory)
    monkeypatch.setattr(upload, "DB_AVAILABLE", True)
    monkeypatch.setattr(upload, "Photo", Photo)
    return factory


def _add_photo(session_factory, photo_id: str, attendees=None) -> None:
    with session_factory() as db:
        db.add(
            Photo(
                id=photo_id,
                filename=f"{photo_id}.jpg",
                file_path=f"/p/{photo_id}.jpg",
                source="upload",
                captured_at=datetime(2026, 7, 28, 22, 59),
                attendees=attendees,
            )
        )
        db.commit()


def _attendees_of(session_factory, photo_id: str):
    with session_factory() as db:
        return db.query(Photo).filter(Photo.id == photo_id).first().attendees


def test_records_attendees_on_the_created_photo(session_factory, monkeypatch):
    from app.routers import upload

    _add_photo(session_factory, "photo_a")
    monkeypatch.setattr(upload, "_record_today_attendees", lambda: ["太郎", "花子"])

    upload.record_attendees_background("photo_a")

    assert _attendees_of(session_factory, "photo_a") == ["太郎", "花子"]


def test_targets_the_id_passed_in_not_another_photo(session_factory, monkeypatch):
    # 渡された photo_id だけを更新すること（隣の写真の attendees を上書きしない）
    from app.routers import upload

    _add_photo(session_factory, "photo_a")
    _add_photo(session_factory, "photo_a_1")
    monkeypatch.setattr(upload, "_record_today_attendees", lambda: ["太郎"])

    upload.record_attendees_background("photo_a_1")

    assert _attendees_of(session_factory, "photo_a_1") == ["太郎"]
    assert _attendees_of(session_factory, "photo_a") is None


def test_no_attendees_leaves_the_record_untouched(session_factory, monkeypatch):
    from app.routers import upload

    _add_photo(session_factory, "photo_a", attendees=["前の値"])
    monkeypatch.setattr(upload, "_record_today_attendees", lambda: None)

    upload.record_attendees_background("photo_a")

    assert _attendees_of(session_factory, "photo_a") == ["前の値"]


def test_ics_failure_does_not_propagate(session_factory, monkeypatch):
    # 写真の保存は成立させる（best-effort）。例外はログのみで飲み込む
    from app.routers import upload

    def boom():
        raise RuntimeError("ICS down")

    _add_photo(session_factory, "photo_a")
    monkeypatch.setattr(upload, "_record_today_attendees", boom)

    upload.record_attendees_background("photo_a")

    assert _attendees_of(session_factory, "photo_a") is None
