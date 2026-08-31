"""Session information endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..read_only_access import get_authenticated_email, is_read_only_request

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])


@router.get("/session")
async def get_session(request: Request) -> dict[str, Any]:
    """Return current access mode resolved from Cloudflare headers."""
    read_only = is_read_only_request(request)
    return {
        "read_only": read_only,
        "can_write": not read_only,
        "authenticated_email": get_authenticated_email(request),
    }
