"""Tests for the GCS-missing photo purge script ."""

import argparse
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, List

import pytest

from app.storage.gcs_storage import GCSStorageHandler
from scripts.maintenance import purge_photos_missing_in_gcs as purge_script


class _FakeQuery:
    """SQLAlchemy の query().options().filter().all() だけを満たす最小のフェイク."""

    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows

    def options(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":
        return self

    def all(self) -> List[Any]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows
        self.committed = False
        self.closed = False

    def query(self, model: Any) -> _FakeQuery:
        return _FakeQuery(self._rows)

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


def _photo(photo_id: str, day: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=photo_id,
        captured_at=datetime(2025, 9, day, tzinfo=timezone.utc),
        deleted_at=None,
    )


@pytest.fixture()
def patched(monkeypatch: pytest.MonkeyPatch):
    """handler / SessionLocal / GCS 一覧を差し替えるヘルパを返す."""

    def apply(rows: List[Any], stored: set[str]) -> _FakeSession:
        session = _FakeSession(rows)
        monkeypatch.setattr(
            purge_script, "get_storage_handler", lambda: GCSStorageHandler()
        )
        monkeypatch.setattr(purge_script, "SessionLocal", lambda: session)
        monkeypatch.setattr(
            purge_script, "list_stored_photo_ids", lambda handler: stored
        )
        return session

    return apply


def test_lists_photo_ids_from_blob_names() -> None:
    """photos/<id>.jpg から ID を切り出し、jpg 以外は数えない."""
    handler = GCSStorageHandler()
    handler._client = SimpleNamespace(
        list_blobs=lambda bucket, prefix: [
            SimpleNamespace(name="photos/a1c29e1e-cfb7-4a2d-82a5-9a5a6ca30d29.jpg"),
            SimpleNamespace(name="photos/photo_20260812_104934.jpg"),
            SimpleNamespace(name="photos/thumb.png"),
        ]
    )

    assert purge_script.list_stored_photo_ids(handler) == {
        "a1c29e1e-cfb7-4a2d-82a5-9a5a6ca30d29",
        "photo_20260812_104934",
    }


def test_purges_photos_without_an_original(patched: Any) -> None:
    """GCS に原本の無い写真だけ deleted_at が入り commit される."""
    kept, other, lost = _photo("kept", 1), _photo("other", 2), _photo("lost", 3)
    session = patched([kept, other, lost], {"kept", "other"})

    assert purge_script.purge() == 1
    assert kept.deleted_at is None
    assert other.deleted_at is None
    assert lost.deleted_at is not None
    assert session.committed


def test_dry_run_does_not_commit(patched: Any) -> None:
    """--dry-run は件数だけ返して書き込まない."""
    lost = _photo("lost", 2)
    session = patched([_photo("kept", 1), lost], {"kept"})

    assert purge_script.purge(dry_run=True) == 1
    assert lost.deleted_at is None
    assert not session.committed


def test_aborts_when_bucket_listing_is_empty(patched: Any) -> None:
    """GCS 一覧が空なら（障害の疑い）DB に触れない."""
    lost = _photo("lost")
    session = patched([lost], set())

    assert purge_script.purge() == 0
    assert lost.deleted_at is None
    assert not session.committed


def test_aborts_when_missing_ratio_exceeds_limit(patched: Any) -> None:
    """欠損率が上限を超えたら中止する（設定ずれで全消しするのを防ぐ）."""
    photos = [_photo("a", 1), _photo("b", 2), _photo("c", 3)]
    session = patched(photos, {"a"})

    assert purge_script.purge(max_ratio=0.5) == 0
    assert all(p.deleted_at is None for p in photos)
    assert not session.committed


def test_force_overrides_the_ratio_limit(patched: Any) -> None:
    """--force なら上限を超えても実行する."""
    photos = [_photo("a", 1), _photo("b", 2), _photo("c", 3)]
    session = patched(photos, {"a"})

    assert purge_script.purge(max_ratio=0.5, force=True) == 2
    assert session.committed


@pytest.mark.parametrize("value", ["nan", "inf", "-0.1", "1.5"])
def test_rejects_out_of_range_max_ratio(value: str) -> None:
    """nan や範囲外の --max-ratio を弾く（黙って安全弁が消えるのを防ぐ）."""
    with pytest.raises(argparse.ArgumentTypeError):
        purge_script.ratio_arg(value)


@pytest.mark.parametrize("value", ["0", "0.5", "1"])
def test_accepts_valid_max_ratio(value: str) -> None:
    """0〜1 は通す."""
    assert purge_script.ratio_arg(value) == float(value)


def test_skips_when_storage_is_not_gcs(monkeypatch: pytest.MonkeyPatch) -> None:
    """ローカルストレージ環境では誤判定を避けて何もしない."""
    monkeypatch.setattr(purge_script, "get_storage_handler", lambda: SimpleNamespace())

    assert purge_script.purge() == 0
