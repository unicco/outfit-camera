"""Authentication helpers for API endpoints."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from typing import Annotated, Literal, Optional

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuthenticatedActor:
    """Identity information returned by authentication dependencies."""

    identifier: Optional[str]
    source: Literal["cloudflare", "token", "development-bypass"]


CfAccessEmailHeader = Annotated[
    Optional[str],
    Header(alias="Cf-Access-Authenticated-User-Email", convert_underscores=False),
]

CfAccessJwtHeader = Annotated[
    Optional[str],
    Header(alias="Cf-Access-Jwt-Assertion", convert_underscores=False),
]


def require_external_rental_auth(
    cf_access_email: CfAccessEmailHeader = None,
    cf_access_jwt: CfAccessJwtHeader = None,
    authorization: Annotated[Optional[str], Header()] = None,
) -> AuthenticatedActor:
    """Validate authentication for external rental APIs.

    In production, requests must be authenticated by Cloudflare Access
    (cookies → Cf-Access headers) or provide a bearer token that matches
    EXTERNAL_RENTAL_API_TOKEN. Development environments keep the previous
    behaviour for ease of local testing.
    """
    env = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or "development").lower()
    auth_disabled = (
        os.getenv("EXTERNAL_RENTAL_AUTH_DISABLED", "false").lower() == "true"
    )
    auth_mode = os.getenv("EXTERNAL_RENTAL_AUTH_REQUIRED", "auto").lower()

    if auth_mode not in {"true", "false", "auto"}:
        logger.warning(
            "Unexpected EXTERNAL_RENTAL_AUTH_REQUIRED value '%s'; defaulting to auto",
            auth_mode,
        )
        auth_mode = "auto"

    enforce_auth = auth_mode == "true" or (auth_mode == "auto" and env == "production")
    if auth_disabled:
        enforce_auth = False

    if not enforce_auth:
        if cf_access_email:
            logger.debug(
                "External rental auth bypassed (%s) for %s",
                "development" if env != "production" else "manual-override",
                cf_access_email,
            )
        return AuthenticatedActor(
            identifier=cf_access_email,
            source="development-bypass",
        )

    if cf_access_email:
        logger.info(
            "External rental request authenticated via Cloudflare Access for %s",
            cf_access_email,
        )
        if not cf_access_jwt:
            logger.debug("Cloudflare JWT missing; continuing with email header only")
        return AuthenticatedActor(identifier=cf_access_email, source="cloudflare")

    token = os.getenv("EXTERNAL_RENTAL_API_TOKEN")
    if token and authorization:
        scheme, _, credential = authorization.partition(" ")
        if scheme.lower() == "bearer" and credential:
            if secrets.compare_digest(token.strip(), credential.strip()):
                logger.info("External rental request authenticated via API token")
                return AuthenticatedActor(identifier=None, source="token")

    logger.warning("External rental request rejected: missing authentication headers")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required for external rental APIs",
        headers={"WWW-Authenticate": "Bearer"},
    )


__all__ = ["AuthenticatedActor", "require_external_rental_auth"]
