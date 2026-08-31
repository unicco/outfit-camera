"""album_id が渡されないときの追加先の決まり方。

albums().list() は現行スコープで必ず 403 になるため、名前から ID を引く create_album()
には落とさず、GOOGLE_PHOTOS_BATCH_ALBUM_ID の ID を直接使う必要がある。
"""

from types import SimpleNamespace
from typing import Any

import pytest

from app.storage.google_photos_storage import GooglePhotosStorageHandler

ENV_ALBUM_ID = "ALBUM_FROM_ENV"
CREDS = SimpleNamespace(token="ACCESS_TOKEN")


class _FakeMediaItems:
    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    def batchCreate(
        self, body: dict[str, Any]
    ):  # noqa: N802 (Google API の名前に合わせる)
        self._captured["body"] = body
        return SimpleNamespace(
            execute=lambda: {
                "newMediaItemResults": [
                    {
                        "mediaItem": {"id": "MEDIA_ITEM_ID"},
                        "status": {"message": "Success"},
                    }
                ]
            }
        )


class _FakeService:
    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    def mediaItems(self):  # noqa: N802 (Google API の名前に合わせる)
        return _FakeMediaItems(self._captured)


@pytest.fixture
def captured() -> dict[str, Any]:
    """batchCreate に渡された body を受け取る箱."""
    return {}


@pytest.fixture(autouse=True)
def _patch_google_api(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]
) -> None:
    """Google API 呼び出しを差し替える。handler の生成は env を設定した後に各テストで行う."""
    monkeypatch.setattr(
        "app.storage.google_photos_storage.build",
        lambda *a, **kw: _FakeService(captured),
    )
    monkeypatch.setattr(
        "app.storage.google_photos_storage.requests.post",
        lambda *a, **kw: SimpleNamespace(status_code=200, text="UPLOAD_TOKEN"),
    )


@pytest.fixture
def photo(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"jpeg-bytes")
    return p


def test_env_album_id_is_used_without_calling_create_album(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any], photo
) -> None:
    """album_id 未指定なら env の ID を使い、create_album() は呼ばない."""
    monkeypatch.setenv("GOOGLE_PHOTOS_BATCH_ALBUM_ID", ENV_ALBUM_ID)
    handler = GooglePhotosStorageHandler()

    def _fail():
        raise AssertionError(
            "create_album() を呼んではいけない（albums().list() が 403 になる）"
        )

    monkeypatch.setattr(handler, "create_album", _fail)

    result = handler._upload_photo_impl(str(photo), "desc", CREDS)

    assert result == "MEDIA_ITEM_ID"
    assert captured["body"]["albumId"] == ENV_ALBUM_ID


def test_explicit_album_id_wins_over_env(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any], photo
) -> None:
    """呼び出し側が album_id を渡したらそちらを使う."""
    monkeypatch.setenv("GOOGLE_PHOTOS_BATCH_ALBUM_ID", ENV_ALBUM_ID)
    handler = GooglePhotosStorageHandler()

    handler._upload_photo_impl(str(photo), "desc", CREDS, album_id="EXPLICIT")

    assert captured["body"]["albumId"] == "EXPLICIT"


def test_falls_back_to_create_album_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any], photo
) -> None:
    """env が空なら従来どおり create_album() に落ちる（開発環境向けの逃げ道）."""
    monkeypatch.delenv("GOOGLE_PHOTOS_BATCH_ALBUM_ID", raising=False)
    handler = GooglePhotosStorageHandler()
    monkeypatch.setattr(handler, "create_album", lambda: "ALBUM_FROM_CREATE")

    handler._upload_photo_impl(str(photo), "desc", CREDS)

    assert captured["body"]["albumId"] == "ALBUM_FROM_CREATE"


def test_no_album_id_when_create_album_fails(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any], photo
) -> None:
    """create_album() が None を返しても albumId 無しでアップロードは続ける."""
    monkeypatch.delenv("GOOGLE_PHOTOS_BATCH_ALBUM_ID", raising=False)
    handler = GooglePhotosStorageHandler()
    monkeypatch.setattr(handler, "create_album", lambda: None)

    result = handler._upload_photo_impl(str(photo), "desc", CREDS)

    assert result == "MEDIA_ITEM_ID"
    assert "albumId" not in captured["body"]
