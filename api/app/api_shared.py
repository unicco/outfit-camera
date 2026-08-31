"""Shared runtime surface extracted from the removed ``api.py`` monolith.

Permanent home  for the helpers that the api.py monolith
exposed to the routers during the migration: the unified ``get_db`` dependency,
the database-availability flags (``DB_AVAILABLE`` / ``DATABASE_MODE``), the
``PhotoRepository`` / ``Photo`` re-exports with their None fallback, and the
emergency fallback responses. Routers import these from here instead of ``..api``.

Why this is separate from ``app.dependencies``: that module's ``get_db`` yields a
raw ``Session`` and assumes the DB is always importable. The ``get_db`` here is the
degraded-mode variant that yields ``None`` when the database package failed to
import (``DB_AVAILABLE`` False), so endpoints can return 503 instead of crashing.
The routers migrated off api.py depend on that None-fallback semantics, so it is
preserved verbatim here rather than folded into ``app.dependencies.get_db``.
"""

import logging
from typing import Any, Generator

from sqlalchemy.orm import Session

from .settings import get_settings

logger = logging.getLogger(__name__)

# Import database components with fallback
try:
    from .database import get_db as _real_get_db
    from .repositories import PhotoRepository
    from .models import Photo

    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    _real_get_db = None  # type: ignore
    PhotoRepository = None  # type: ignore
    Photo = None  # type: ignore


# Create a unified get_db function (degraded-mode variant, yields None when the
# database package is unavailable — see module docstring).
def get_db() -> Generator[Session | None, None, None]:
    if DB_AVAILABLE and _real_get_db is not None:
        yield from _real_get_db()
    else:
        yield None


# DATABASE_MODE resolved once at import time, mirroring the previous
# module-level constant that lived in the removed app.config .
DATABASE_MODE = get_settings().database_mode

# Database mode validation
if DATABASE_MODE == "required" and not DB_AVAILABLE:
    raise RuntimeError("DATABASE_MODE=required but database imports failed")


def _record_today_attendees() -> list[str] | None:
    """今日のカレンダー参加者（`@名前`）を返す。撮影時に写真へ記録する用.

    ICS 未設定・取得失敗は None（撮影は止めない）。
    ICS 取得は 1 本あたり数秒かかるため呼び出し側はバックグラウンドで実行する
    （upload の `record_attendees_background`）。
    タイムアウトは短縮しない。5 秒では ICS 取得が間に合わず参加者が失われる。
    """
    try:
        # Re-import locally so tests can monkeypatch app.settings.get_settings
        # (the module-level binding above is resolved once at import time).
        from .settings import get_settings
        from .services.calendar_ics import fetch_today_events, unique_attendees

        settings = get_settings()
        if not settings.calendar_ics_urls:
            return None
        events = fetch_today_events(
            settings.calendar_ics_urls,
            redact_title_keywords=settings.calendar_redact_title_keywords,
        )
        return unique_attendees(events) or None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to record today's attendees: %s", exc)
        return None


def get_emergency_photos_response() -> list:
    """Emergency minimal response for photos endpoint."""
    return []


def get_emergency_stats_response() -> dict[str, Any]:
    """Emergency minimal response for stats endpoint."""
    return {
        "database": {"healthy": False, "connection": "unavailable", "total_photos": 0},
        "emergency_mode": True,
    }
