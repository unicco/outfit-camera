"""Google Photos OAuth の state CSRF 検証テスト."""

import time
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import google_photos
from app.storage import google_photos_storage
from app.storage.google_photos_storage import (
    STATE_TTL_SECONDS,
    GooglePhotosStorageHandler,
)


class FakeFlow:
    """google-auth の Flow を模したテスト用スタブ.

    ⚠️ ``code_verifier`` は本物と同じ寿命で模すこと（``authorization_url()`` で
    生成され、無い Flow の ``fetch_token()`` は ``invalid_grant`` で落ちる）。
    ここを省くと verifier を落とす実装が緑のまま通る。
    """

    def __init__(self) -> None:
        self.fetched_code: str | None = None
        self.code_verifier: str | None = None
        self.credentials = SimpleNamespace(to_json=lambda: '{"token": "fake"}')

    def authorization_url(self, **kwargs: object) -> tuple[str, object]:
        state = kwargs["state"]
        self.code_verifier = "verifier-for-" + str(state)
        return f"https://accounts.google.com/o/oauth2/auth?state={state}", state

    def fetch_token(self, code: str | None = None) -> None:
        if not self.code_verifier:
            raise ValueError("(invalid_grant) Missing code verifier.")
        self.fetched_code = code


@pytest.fixture
def handler(tmp_path, monkeypatch: pytest.MonkeyPatch) -> GooglePhotosStorageHandler:
    """認証情報ファイルを実在させたハンドラー + Flow をスタブ化."""
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text("{}")

    instance = GooglePhotosStorageHandler()
    instance.credentials_file = str(creds_file)
    instance.token_file = str(tmp_path / "token.json")

    fake_flow = FakeFlow()
    monkeypatch.setattr(
        google_photos_storage,
        "Flow",
        SimpleNamespace(from_client_secrets_file=lambda *a, **k: fake_flow),
    )
    instance._fake_flow = fake_flow  # テストから参照するため保持
    return instance


def test_initiate_auth_flow_embeds_and_registers_state(
    handler: GooglePhotosStorageHandler,
) -> None:
    """auth URL に state を埋め込み、ストアへ redirect_uri とともに記録する."""
    redirect_uri = "https://coordinate.unicco.app/api/v2/google-photos/oauth2callback"
    auth_url = handler.initiate_auth_flow(redirect_uri)

    assert "state=" in auth_url
    assert len(handler._pending_states) == 1
    (state, (stored_uri, stored_verifier, _expiry)) = next(
        iter(handler._pending_states.items())
    )
    assert f"state={state}" in auth_url
    assert stored_uri == redirect_uri
    # PKCE の verifier も一緒に預かる（コールバックで Flow を作り直すため）
    assert stored_verifier == handler._fake_flow.code_verifier


def test_complete_auth_flow_restores_code_verifier(
    handler: GooglePhotosStorageHandler, monkeypatch: pytest.MonkeyPatch
) -> None:
    """作り直した Flow に authorize 時の code_verifier を戻す.

    戻さないと Google が ``invalid_grant: Missing code verifier`` で弾く。
    """
    handler._write_token = lambda token_json: None  # type: ignore[method-assign]

    handler.initiate_auth_flow("https://cb.example/callback")
    state = next(iter(handler._pending_states))
    issued_verifier = handler._fake_flow.code_verifier

    # コールバックは新しい Flow を作る。verifier を持たない状態から始まる。
    fresh_flow = FakeFlow()
    monkeypatch.setattr(
        google_photos_storage,
        "Flow",
        SimpleNamespace(from_client_secrets_file=lambda *a, **k: fresh_flow),
    )

    assert handler.complete_auth_flow("auth-code", state) is True
    assert fresh_flow.code_verifier == issued_verifier
    assert fresh_flow.fetched_code == "auth-code"


def test_complete_auth_flow_accepts_valid_state(
    handler: GooglePhotosStorageHandler,
) -> None:
    """有効な state ならトークンを書き込み、state をワンタイム消費する."""
    written: list[str] = []
    handler._write_token = lambda token_json: written.append(token_json)  # type: ignore[method-assign]

    handler.initiate_auth_flow("https://cb.example/callback")
    state = next(iter(handler._pending_states))

    assert handler.complete_auth_flow("auth-code", state) is True
    assert written == ['{"token": "fake"}']
    assert handler._fake_flow.fetched_code == "auth-code"
    # ワンタイム消費されている（リプレイ不可）
    assert state not in handler._pending_states


def test_complete_auth_flow_uses_registered_redirect_uri(
    handler: GooglePhotosStorageHandler, monkeypatch: pytest.MonkeyPatch
) -> None:
    """flow 再構築には state 登録時の redirect_uri を使う（引数より優先）."""
    handler._write_token = lambda token_json: None  # type: ignore[method-assign]

    captured: dict[str, object] = {}

    def capturing_factory(*args: object, **kwargs: object):
        captured.update(kwargs)
        return handler._fake_flow

    monkeypatch.setattr(
        google_photos_storage,
        "Flow",
        SimpleNamespace(from_client_secrets_file=capturing_factory),
    )

    registered_uri = "https://cb.example/registered"
    handler.initiate_auth_flow(registered_uri)
    state = next(iter(handler._pending_states))

    # 呼び出し側は別の（食い違った）redirect_uri を渡す
    assert handler.complete_auth_flow(
        "auth-code", state, redirect_uri="https://attacker.example/other"
    )
    assert captured["redirect_uri"] == registered_uri


def test_complete_auth_flow_rejects_replayed_state(
    handler: GooglePhotosStorageHandler,
) -> None:
    """同じ state の 2 回目の使用は拒否される（リプレイ不可）."""
    written: list[str] = []
    handler._write_token = lambda token_json: written.append(token_json)  # type: ignore[method-assign]

    handler.initiate_auth_flow("https://cb.example/callback")
    state = next(iter(handler._pending_states))

    assert handler.complete_auth_flow("auth-code", state) is True
    # 2 回目は state が消費済なので拒否
    assert handler.complete_auth_flow("auth-code", state) is False
    assert len(written) == 1


def test_complete_auth_flow_rejects_unknown_state(
    handler: GooglePhotosStorageHandler,
) -> None:
    """登録されていない state は拒否し、トークンを書き込まない."""
    written: list[str] = []
    handler._write_token = lambda token_json: written.append(token_json)  # type: ignore[method-assign]

    assert handler.complete_auth_flow("auth-code", "bogus-state") is False
    assert written == []
    assert handler._fake_flow.fetched_code is None


def test_complete_auth_flow_rejects_missing_state(
    handler: GooglePhotosStorageHandler,
) -> None:
    """空の state は拒否する."""
    written: list[str] = []
    handler._write_token = lambda token_json: written.append(token_json)  # type: ignore[method-assign]

    assert handler.complete_auth_flow("auth-code", "") is False
    assert written == []


def test_complete_auth_flow_rejects_expired_state(
    handler: GooglePhotosStorageHandler,
) -> None:
    """TTL を過ぎた state は拒否する."""
    written: list[str] = []
    handler._write_token = lambda token_json: written.append(token_json)  # type: ignore[method-assign]

    handler.initiate_auth_flow("https://cb.example/callback")
    state = next(iter(handler._pending_states))
    # 失効時刻を過去へ書き換える
    redirect_uri, code_verifier, _expiry = handler._pending_states[state]
    handler._pending_states[state] = (
        redirect_uri,
        code_verifier,
        time.monotonic() - 1,
    )

    assert handler.complete_auth_flow("auth-code", state) is False
    assert written == []
    assert state not in handler._pending_states  # 期限切れは掃除される


def test_state_ttl_is_reasonable() -> None:
    """TTL は consent を待てる程度に長く、無制限ではないこと."""
    assert 60 <= STATE_TTL_SECONDS <= 3600


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(google_photos.router)
    with TestClient(app) as test_client:
        yield test_client


def test_oauth_callback_requires_state(client: TestClient) -> None:
    """コールバックに state が無ければ 400 で拒否する."""
    response = client.get(
        "/api/v2/google-photos/oauth2callback",
        params={"code": "abc"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "State parameter is required"


def test_oauth_callback_rejects_invalid_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """handler が state 検証で失敗（False）を返したら 400 にする."""
    stub = SimpleNamespace(complete_auth_flow=lambda *a, **k: False)
    monkeypatch.setattr(google_photos, "get_google_photos_handler", lambda: stub)

    response = client.get(
        "/api/v2/google-photos/oauth2callback",
        params={"code": "abc", "state": "mismatch"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Failed to complete authentication"
