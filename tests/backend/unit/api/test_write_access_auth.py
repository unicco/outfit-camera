"""Tests for write-endpoint authentication guard .

`require_write_access` protects mutating wardrobe/outfit/co-occurrence
endpoints as defense-in-depth: in production a request must carry a Cloudflare
Access header or the service token; in non-production it fails open so local
development, tests, and the Pi camera upload path keep working.

The pure-function tests below cover the guard's behaviour without loading any
router, so they always run (including in the minimal CI unit environment). The
router-dependent tests are gated behind ``requires_routers`` because the feature
routers transitively import cv2, which can be unavailable/uninitialisable in a
headless CI (missing libGL); there they skip cleanly rather than fail, and run
fully wherever the full dependency set is present (local, full test job).
"""

from __future__ import annotations

import os
from typing import List, Tuple
from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request

from app.security import require_write_access


def _routers_importable() -> bool:
    """True when the feature routers (and their heavy deps) can be imported."""
    try:
        import app.routers.co_occurrence  # noqa: F401
        import app.routers.outfits  # noqa: F401
        import app.routers.wardrobe  # noqa: F401

        return True
    except Exception:
        return False


requires_routers = pytest.mark.skipif(
    not _routers_importable(),
    reason="feature routers unavailable (heavy deps such as cv2/libGL missing)",
)


def _request(headers: List[Tuple[bytes, bytes]] | None = None) -> Request:
    """Build a minimal Starlette Request carrying only method + headers."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": headers or [],
        }
    )


# --- Guard behaviour (no router / app needed; always runs) ---


def test_fails_open_in_non_production() -> None:
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
        # Should not raise even without any auth headers.
        assert require_write_access(_request()) is None


def test_rejects_unauthenticated_request_in_production() -> None:
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        with pytest.raises(HTTPException) as exc_info:
            require_write_access(_request())
    assert exc_info.value.status_code == 401


def test_accepts_cloudflare_access_email_in_production() -> None:
    headers = [(b"cf-access-authenticated-user-email", b"user@example.com")]
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        assert require_write_access(_request(headers)) is None


def test_accepts_service_token_bearer_in_production() -> None:
    token = "super-secret-write-token"
    headers = [(b"authorization", f"Bearer {token}".encode())]
    with patch.dict(
        os.environ,
        {"ENVIRONMENT": "production", "EXTERNAL_RENTAL_API_TOKEN": token},
        clear=False,
    ):
        assert require_write_access(_request(headers)) is None


def test_rejects_wrong_service_token_in_production() -> None:
    with patch.dict(
        os.environ,
        {"ENVIRONMENT": "production", "EXTERNAL_RENTAL_API_TOKEN": "correct-token"},
        clear=False,
    ):
        with pytest.raises(HTTPException) as exc_info:
            require_write_access(_request([(b"authorization", b"Bearer wrong-token")]))
    assert exc_info.value.status_code == 401


def test_bypass_env_disables_enforcement_in_production() -> None:
    with patch.dict(
        os.environ,
        {"ENVIRONMENT": "production", "EXTERNAL_RENTAL_AUTH_BYPASS": "true"},
        clear=False,
    ):
        assert require_write_access(_request()) is None


# --- Endpoint wiring (exercised through the real app) ---


@requires_routers
def test_wardrobe_delete_requires_auth_in_production(client_v2) -> None:
    """Production request without auth is rejected before reaching the handler."""
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        response = client_v2.delete("/api/v2/wardrobe/items/does-not-exist")
    assert response.status_code == 401


@requires_routers
def test_wardrobe_delete_passes_auth_then_404_with_cf_header(client_v2) -> None:
    """With a CF Access header the guard passes; missing item then yields 404."""
    headers = {"Cf-Access-Authenticated-User-Email": "user@example.com"}
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        response = client_v2.delete(
            "/api/v2/wardrobe/items/does-not-exist", headers=headers
        )
    assert response.status_code == 404


@requires_routers
def test_wardrobe_delete_open_in_development(client_v2) -> None:
    """Non-production keeps the endpoint reachable without auth (fail-open)."""
    with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
        response = client_v2.delete("/api/v2/wardrobe/items/does-not-exist")
    assert response.status_code == 404


@requires_routers
def test_co_occurrence_batch_migrate_requires_auth_in_production(client_v2) -> None:
    """The formerly TODO-only batch endpoint now enforces auth in production."""
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        response = client_v2.post("/api/v2/co-occurrence/batch/migrate")
    assert response.status_code == 401


# --- Route-introspection guardrails (catch future misses) ---


def _dependency_calls(route) -> set:
    """Collect every callable in a route's flattened dependency tree."""
    calls: set = set()
    stack = [route.dependant]
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            calls.add(dep.call)
        stack.extend(dep.dependencies)
    return calls


# (METHOD, PATH) of every mutating endpoint that must carry require_write_access.
GUARDED_MUTATING_ROUTES = {
    ("POST", "/api/v2/wardrobe/items"),
    ("PUT", "/api/v2/wardrobe/items/{item_id}"),
    ("DELETE", "/api/v2/wardrobe/items/{item_id}"),
    ("POST", "/api/v2/wardrobe/items/{item_id}/images"),
    ("PUT", "/api/v2/wardrobe/items/{item_id}/sale-info"),
    ("POST", "/api/v2/outfits/record"),
    ("DELETE", "/api/v2/outfits/photo/{photo_id}"),
    ("POST", "/api/v2/co-occurrence/batch/process"),
    ("POST", "/api/v2/co-occurrence/batch/migrate"),
}

# Read endpoints that must stay open (POST verb but no mutation / pure read).
OPEN_READ_ROUTES = {
    ("POST", "/api/v2/outfits/batch/simple"),
    ("POST", "/api/v2/co-occurrence/category-probability"),
    ("GET", "/api/v2/co-occurrence/items/{item_id}/best-matches"),
}


def _route_index() -> dict:
    """Index the guarded routers directly.

    The routers' ``.routes`` already carry their prefix, so paths match the live
    app. Introspecting the routers (rather than ``app.main:app``) avoids the
    app's dynamic loader silently skipping modules, which would make an app-level
    scan spuriously report routes as missing.
    """
    from app.routers.co_occurrence import router as co_occurrence_router
    from app.routers.outfits import router as outfit_router
    from app.routers.wardrobe import router as wardrobe_router

    index = {}
    for router in (wardrobe_router, outfit_router, co_occurrence_router):
        for route in router.routes:
            for method in getattr(route, "methods", set()) or set():
                index[(method, route.path)] = route
    return index


@requires_routers
def test_all_mutating_write_endpoints_are_guarded() -> None:
    index = _route_index()
    missing = []
    for key in GUARDED_MUTATING_ROUTES:
        route = index.get(key)
        if route is None:
            missing.append((key, "route not found"))
        elif require_write_access not in _dependency_calls(route):
            missing.append((key, "no require_write_access dependency"))
    assert not missing, f"unguarded mutating routes: {missing}"


@requires_routers
def test_read_endpoints_remain_open() -> None:
    index = _route_index()
    for key in OPEN_READ_ROUTES:
        route = index.get(key)
        assert route is not None, f"route not found: {key}"
        assert require_write_access not in _dependency_calls(
            route
        ), f"read endpoint unexpectedly guarded: {key}"
