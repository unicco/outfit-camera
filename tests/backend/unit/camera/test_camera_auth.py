#!/usr/bin/env python3
"""カメラサービス（Pi :8001）の共有トークン認証 middleware のテスト.

camera/camera_service.py はモジュール読み込み時に CameraService() を生成し、
`CAMERA_API_TOKEN` を読む。enforce 有無を切り替えるためトークンごとに
importlib で別インスタンスとして読み込む（simulation モードでハードウェア回避）。
"""

import importlib.util
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

CAMERA_SERVICE_PATH = (
    Path(__file__).resolve().parents[4] / "camera" / "camera_service.py"
)
GOOD_TOKEN = "unit-test-token-abc123"


def _load_service(token):
    """指定トークンで camera_service モジュールを新規ロードする（失敗時は skip）."""
    os.environ["CAMERA_MODE"] = "simulation"
    os.environ["DISABLE_AI_FEATURES"] = "true"
    os.environ["PIR_ENABLED"] = "false"
    if token is None:
        os.environ.pop("CAMERA_API_TOKEN", None)
    else:
        os.environ["CAMERA_API_TOKEN"] = token

    spec = importlib.util.spec_from_file_location(
        f"camsvc_{token}", CAMERA_SERVICE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - 環境にカメラ依存が無い場合
        pytest.skip(f"camera_service をロードできない: {exc}")
    return module


def _client(module, host):
    """送信元 IP を指定した TestClient を返す."""
    return TestClient(module.app, client=(host, 50000))


@pytest.fixture(scope="module")
def enforced():
    return _load_service(GOOD_TOKEN)


def test_exempt_path_no_token(enforced):
    """/status は認証免除で 200."""
    assert _client(enforced, "100.64.1.2").get("/status").status_code == 200


def test_protected_requires_token(enforced):
    """保護対象は非 localhost + トークン無しで 401."""
    assert _client(enforced, "100.64.1.2").get("/pir/status").status_code == 401


def test_shutdown_requires_token(enforced):
    """本 Issue の本丸: 遠隔停止 /shutdown はトークン無しで 401（回帰防止）."""
    assert _client(enforced, "100.64.1.2").post("/shutdown").status_code == 401


def test_protected_rejects_wrong_token(enforced):
    resp = _client(enforced, "100.64.1.2").get(
        "/pir/status", headers={"X-Camera-Token": "wrong"}
    )
    assert resp.status_code == 401


def test_protected_accepts_header_token(enforced):
    resp = _client(enforced, "100.64.1.2").get(
        "/pir/status", headers={"X-Camera-Token": GOOD_TOKEN}
    )
    assert resp.status_code == 200


def test_protected_accepts_query_token(enforced):
    """<img> ストリーム向けの ?token= 経路."""
    resp = _client(enforced, "100.64.1.2").get(f"/pir/status?token={GOOD_TOKEN}")
    assert resp.status_code == 200


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_localhost_exempt(enforced, host):
    """キオスク（Pi localhost 直アクセス）はトークン無しで通る（IPv4/IPv6 loopback）."""
    assert _client(enforced, host).get("/pir/status").status_code == 200


def test_health_reports_auth_enforced(enforced):
    """外形監視向け: /health が auth_enforced=true を返す（fail-open 検知用）."""
    body = _client(enforced, "100.64.1.2").get("/health").json()
    assert body["auth_enforced"] is True


def test_health_reports_auth_disabled_when_unset():
    """トークン未設定なら /health は auth_enforced=false を返す."""
    module = _load_service(None)
    body = _client(module, "100.64.1.2").get("/health").json()
    assert body["auth_enforced"] is False


def test_preflight_not_blocked(enforced):
    """CORS preflight(OPTIONS) は認証で潰さない."""
    resp = _client(enforced, "100.64.1.2").options(
        "/shutdown",
        headers={
            "Origin": "https://coordinate.unicco.app",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 200


def test_fail_open_when_token_unset():
    """CAMERA_API_TOKEN 未設定なら enforce しない（キオスク保護のブリック防止）."""
    module = _load_service(None)
    assert _client(module, "100.64.1.2").get("/pir/status").status_code == 200


def test_cors_rejects_unknown_origin(enforced):
    resp = _client(enforced, "100.64.1.2").get(
        "/status", headers={"Origin": "https://evil.example.com"}
    )
    assert resp.headers.get("access-control-allow-origin") is None


def test_cors_allows_tailscale_origin(enforced):
    resp = _client(enforced, "100.64.1.2").get(
        "/status", headers={"Origin": "http://100.64.0.10:3000"}
    )
    assert resp.headers.get("access-control-allow-origin") == "http://100.64.0.10:3000"
    assert resp.headers.get("access-control-allow-credentials") is None


def test_cors_allows_pi_entrance_local(enforced):
    """Caddy 非経由の LAN 直アクセス（pi-camera.local）の fetch/preflight を通す."""
    origin = "http://pi-camera.local:3000"
    resp = _client(enforced, "100.64.1.2").get("/status", headers={"Origin": origin})
    assert resp.headers.get("access-control-allow-origin") == origin
