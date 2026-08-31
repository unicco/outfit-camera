"""Middleware to block write operations for read-only users."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from ..read_only_access import (
    READ_ONLY_METHODS,
    get_authenticated_email,
    is_read_only_request,
)


def setup_read_only_middleware(app: FastAPI) -> None:
    """Register middleware enforcing read-only mode on mutating requests."""

    @app.middleware("http")
    async def enforce_read_only_mode(request: Request, call_next):
        if request.method.upper() in READ_ONLY_METHODS and is_read_only_request(
            request
        ):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": "This account is currently in read-only mode.",
                    "read_only": True,
                    "authenticated_email": get_authenticated_email(request),
                },
            )

        return await call_next(request)
