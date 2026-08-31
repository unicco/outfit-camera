"""Tests for read-only access mode via Cloudflare authenticated email."""

from __future__ import annotations

from unittest.mock import patch

import app.external_rental_models  # noqa: F401


def test_session_endpoint_returns_read_only_for_configured_email(client_v2) -> None:
    headers = {"Cf-Access-Authenticated-User-Email": "viewer@example.com"}
    with patch.dict(
        "os.environ",
        {"READ_ONLY_CLOUDFLARE_EMAILS": "viewer@example.com"},
        clear=False,
    ):
        response = client_v2.get("/api/v2/auth/session", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert payload["can_write"] is False
    assert payload["authenticated_email"] == "viewer@example.com"


def test_session_endpoint_returns_writable_for_unconfigured_email(client_v2) -> None:
    headers = {"Cf-Access-Authenticated-User-Email": "editor@example.com"}
    with patch.dict(
        "os.environ",
        {"READ_ONLY_CLOUDFLARE_EMAILS": "viewer@example.com"},
        clear=False,
    ):
        response = client_v2.get("/api/v2/auth/session", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is False
    assert payload["can_write"] is True
    assert payload["authenticated_email"] == "editor@example.com"


def test_mutating_request_is_blocked_for_read_only_user(client_v2) -> None:
    headers = {"Cf-Access-Authenticated-User-Email": "viewer@example.com"}
    with patch.dict(
        "os.environ",
        {"READ_ONLY_CLOUDFLARE_EMAILS": "viewer@example.com"},
        clear=False,
    ):
        response = client_v2.post("/api/v2/outfits/record", json={}, headers=headers)

    assert response.status_code == 403
    payload = response.json()
    assert payload["read_only"] is True
    assert "read-only" in payload["detail"]


def test_mutating_request_continues_for_non_read_only_user(client_v2) -> None:
    headers = {"Cf-Access-Authenticated-User-Email": "editor@example.com"}
    with patch.dict(
        "os.environ",
        {"READ_ONLY_CLOUDFLARE_EMAILS": "viewer@example.com"},
        clear=False,
    ):
        response = client_v2.post("/api/v2/outfits/record", json={}, headers=headers)

    # Request reaches endpoint and fails by payload validation, not read-only middleware.
    assert response.status_code != 403
