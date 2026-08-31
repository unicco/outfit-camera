"""Google Photos への後追いアップロードの結果ログを固定する.

固定するのは 2 つ。

1. `upload_to_google_photos_background` が各分岐で返す結果文字列
2. `log_google_photos_upload_result` が `"uploaded"` 以外を ERROR に落とすこと
   （未知の戻り値も失敗側へ倒す fail-safe の向き）

`app.routers.upload` は cv2 を transitively import するため、headless CI
（libGL 不在）では import できない。`test_upload_attendees_background.py` と
同じ理由で skipif ゲートを置き、フル依存の環境でだけ走らせる。
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytest


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

PHOTO_ID = "photo_20260828_120000"
TIMESTAMP = datetime(2026, 8, 28, 12, 0)


class _Handler:
    """`get_google_photos_handler()` の戻り値を最小限で模す."""

    def __init__(self, authenticated: bool, media_item_id=None, raises=False):
        self._authenticated = authenticated
        self._media_item_id = media_item_id
        self._raises = raises

    def is_authenticated(self) -> bool:
        if self._raises:
            raise RuntimeError("boom")
        return self._authenticated

    def upload_photo(self, path: str, description: str):
        return self._media_item_id


def _run_background(monkeypatch, handler) -> str:
    from app.routers import upload

    monkeypatch.setattr(
        "app.storage.storage_factory.get_google_photos_handler", lambda: handler
    )
    monkeypatch.setattr(upload, "DB_AVAILABLE", False)
    return upload.upload_to_google_photos_background(PHOTO_ID, b"jpeg-bytes", TIMESTAMP)


def test_unauthenticated_returns_unauthenticated(monkeypatch):
    """未認証を成功と報告しない（#1176 の事故そのものの形）."""
    assert _run_background(monkeypatch, _Handler(authenticated=False)) == (
        "unauthenticated"
    )


def test_successful_upload_returns_uploaded(monkeypatch):
    handler = _Handler(authenticated=True, media_item_id="APgFom-xxxx")

    assert _run_background(monkeypatch, handler) == "uploaded"


def test_missing_media_item_id_returns_failed(monkeypatch):
    handler = _Handler(authenticated=True, media_item_id=None)

    assert _run_background(monkeypatch, handler) == "failed"


def test_exception_returns_error(monkeypatch):
    assert _run_background(monkeypatch, _Handler(authenticated=True, raises=True)) == (
        "error"
    )


def test_temp_file_cleanup_failure_keeps_upload_result(monkeypatch):
    """後片付けの失敗でアップロード成功を "error" に化けさせない.

    `finally` 内の例外は `return` 値を捨てて外側の except に落ちるため、
    握り潰さないと「上がっているのに上がっていない」と報告してしまう。
    """
    import os as os_module

    handler = _Handler(authenticated=True, media_item_id="APgFom-xxxx")

    def _boom(path):
        raise OSError("device busy")

    monkeypatch.setattr(os_module, "unlink", _boom)

    assert _run_background(monkeypatch, handler) == "uploaded"


def _log_result(caplog, result):
    from app.routers import upload

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=upload.logger.name):
        upload.log_google_photos_upload_result(PHOTO_ID, result)
    assert len(caplog.records) == 1
    return caplog.records[0]


def test_uploaded_is_logged_as_success(caplog):
    record = _log_result(caplog, "uploaded")

    assert record.levelno == logging.INFO
    assert "✅" in record.message
    assert PHOTO_ID in record.message


@pytest.mark.parametrize("result", ["unauthenticated", "failed", "error"])
def test_known_failures_are_logged_as_error(caplog, result):
    record = _log_result(caplog, result)

    assert record.levelno == logging.ERROR
    assert "✅" not in record.message
    assert result in record.message


@pytest.mark.parametrize("result", [None, "", "something-new"])
def test_unknown_result_falls_back_to_error(caplog, result):
    """未知の戻り値を成功と読まない（戻り値を返し忘れても ✅ に戻らない）."""
    record = _log_result(caplog, result)

    assert record.levelno == logging.ERROR
    assert "✅" not in record.message
