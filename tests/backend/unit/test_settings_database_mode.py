"""Tests for DATABASE_MODE resolution in the unified Settings .

Before the config-module unification, ``app.config`` defaulted DATABASE_MODE to
``optional`` while ``app.settings`` rejected ``optional`` with a ValueError, so
every ``get_settings()`` code path crashed when the environment set
``DATABASE_MODE=optional``. Settings now normalizes ``optional`` to ``fallback``
with a warning. These four cases are the issue's acceptance criteria.
"""

import pytest

from app.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """get_settings is lru_cached; reset it around each case."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.unit
def test_database_mode_unset_defaults_to_fallback(monkeypatch):
    monkeypatch.delenv("DATABASE_MODE", raising=False)

    assert get_settings().database_mode == "fallback"


@pytest.mark.unit
def test_database_mode_fallback_is_accepted(monkeypatch):
    monkeypatch.setenv("DATABASE_MODE", "fallback")

    assert get_settings().database_mode == "fallback"


@pytest.mark.unit
def test_database_mode_optional_is_normalized_to_fallback_with_warning(monkeypatch):
    monkeypatch.setenv("DATABASE_MODE", "optional")

    with pytest.warns(UserWarning, match="DATABASE_MODE=optional is deprecated"):
        settings = get_settings()

    assert settings.database_mode == "fallback"


@pytest.mark.unit
def test_database_mode_invalid_value_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_MODE", "bogus")

    with pytest.raises(ValueError, match="Invalid DATABASE_MODE"):
        get_settings()


@pytest.mark.unit
def test_database_mode_required_still_accepted(monkeypatch):
    monkeypatch.setenv("DATABASE_MODE", "required")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://u:strongpw@localhost:5432/coordinate_db"
    )

    assert get_settings().database_mode == "required"


@pytest.mark.unit
def test_db_enabled_reflects_database_url():
    assert Settings(database_url=None).db_enabled is False
    assert (
        Settings(
            database_url="postgresql://u:strongpw@localhost:5432/coordinate_db"
        ).db_enabled
        is True
    )
