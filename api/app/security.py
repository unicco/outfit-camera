"""Security helpers for FastAPI endpoints."""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import HTTPException, Request, status

CF_ACCESS_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"
CF_ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion"
SERVICE_TOKEN_HEADER = "X-External-Rental-Token"  # noqa: S105 ヘッダ名。値ではない
AUTHORIZATION_HEADER = "Authorization"
ENVIRONMENT_ENV = "ENVIRONMENT"
# Reused as the generic service token for all app-layer auth (rental +
# wardrobe/outfit/co-occurrence write access). The env name is kept
# for backward compatibility with the already-provisioned production secret.
SERVICE_TOKEN_ENV = "EXTERNAL_RENTAL_API_TOKEN"  # noqa: S105 env 変数名。値ではない
AUTH_BYPASS_ENV = "EXTERNAL_RENTAL_AUTH_BYPASS"


def _enforce_request_auth(request: Request, *, detail: str) -> None:
    """Shared auth check: allow Cloudflare Access requests or a valid service token.

    In production we expect requests to arrive through Cloudflare Access, which
    injects the CF-Access headers. For non-production environments we keep the
    behaviour unchanged (fail-open) to avoid disrupting local development,
    the Raspberry Pi camera uploads (Tailscale, no CF headers), and tests.
    """
    if _auth_not_required():
        return

    if _has_cloudflare_access_headers(request):
        return

    expected_token = _get_expected_service_token()
    provided_token = _extract_token_from_request(request)
    if (
        expected_token
        and provided_token
        and secrets.compare_digest(provided_token, expected_token)
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def require_authenticated_request(request: Request) -> None:
    """Ensure the request passed authentication before mutating rental data."""
    _enforce_request_auth(
        request, detail="Authentication required for external rental endpoints."
    )


def require_write_access(request: Request) -> None:
    """Ensure mutating wardrobe/outfit/co-occurrence requests are authenticated.

    Defense-in-depth: even if the Cloudflare edge is bypassed
    (origin reached directly), production mutations require a Cloudflare Access
    header or the service token. Read endpoints and the Pi upload/ingest paths
    are intentionally not covered here (residual-risk notes).
    """
    _enforce_request_auth(request, detail="Authentication required.")


def _auth_not_required() -> bool:
    """Return True when the strict auth check should be skipped."""
    environment = os.getenv(ENVIRONMENT_ENV, "development").lower()
    if environment != "production":
        return True
    bypass = os.getenv(AUTH_BYPASS_ENV, "false").lower() == "true"
    return bypass


def _has_cloudflare_access_headers(request: Request) -> bool:
    """Detect Cloudflare Access headers injected after successful auth."""
    if request.headers.get(CF_ACCESS_EMAIL_HEADER):
        return True
    if request.headers.get(CF_ACCESS_JWT_HEADER):
        return True
    return False


def _get_expected_service_token() -> Optional[str]:
    """Return the configured service token if present."""
    token = os.getenv(SERVICE_TOKEN_ENV, "").strip()
    return token or None


def _extract_token_from_request(request: Request) -> Optional[str]:
    """Extract service token from custom header or Authorization bearer token."""
    header_token = request.headers.get(SERVICE_TOKEN_HEADER, "").strip()
    if header_token:
        return header_token

    auth_header = request.headers.get(AUTHORIZATION_HEADER)
    if not auth_header:
        return None

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None
