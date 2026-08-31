"""Read-only access control helpers.

Cloudflare Access 認証メールに基づいて閲覧専用モードを判定する。
"""

from __future__ import annotations

import os
from typing import Optional, Set

from fastapi import Request

CF_ACCESS_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"
READ_ONLY_EMAILS_ENV = "READ_ONLY_CLOUDFLARE_EMAILS"
READ_ONLY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def get_configured_read_only_emails() -> Set[str]:
    """Return configured read-only user emails (normalized to lowercase)."""
    raw = os.getenv(READ_ONLY_EMAILS_ENV, "")
    if not raw:
        return set()

    emails: set[str] = set()
    normalized = raw.replace(";", ",")
    for token in normalized.split(","):
        candidate = token.strip().lower()
        if candidate:
            emails.add(candidate)
    return emails


def get_authenticated_email(request: Request) -> Optional[str]:
    """Extract Cloudflare authenticated email from request headers."""
    email = (request.headers.get(CF_ACCESS_EMAIL_HEADER) or "").strip().lower()
    return email or None


def is_read_only_request(request: Request) -> bool:
    """Return True when the current request should be treated as read-only."""
    email = get_authenticated_email(request)
    if not email:
        return False
    return email in get_configured_read_only_emails()
