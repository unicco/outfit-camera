"""Tests for DATABASE_URL validation in Settings .

Local development legitimately uses the ``coordinate_pass`` default and only
gets a warning. Production opts into a hard failure via
``REQUIRE_SECURE_DB_CREDENTIALS=true`` so the API cannot silently boot with the
default password.
"""

import pytest

from app.settings import SecurityWarning, Settings

DEFAULT_URL = (
    "postgresql://coordinate_user:coordinate_pass@localhost:5432/coordinate_db"
)
STRONG_URL = (
    "postgresql://coordinate_user:rotated-strong-value-xyz@localhost:5432/coordinate_db"
)


@pytest.mark.unit
def test_default_password_only_warns_without_flag(monkeypatch):
    monkeypatch.delenv("REQUIRE_SECURE_DB_CREDENTIALS", raising=False)

    with pytest.warns(SecurityWarning):
        settings = Settings(database_url=DEFAULT_URL)

    assert settings.database_url == DEFAULT_URL


@pytest.mark.unit
def test_default_password_raises_when_flag_enabled(monkeypatch):
    monkeypatch.setenv("REQUIRE_SECURE_DB_CREDENTIALS", "true")

    with pytest.raises(ValueError, match="Default database credentials"):
        Settings(database_url=DEFAULT_URL)


@pytest.mark.unit
def test_strong_password_passes_with_flag_enabled(monkeypatch):
    monkeypatch.setenv("REQUIRE_SECURE_DB_CREDENTIALS", "true")

    settings = Settings(database_url=STRONG_URL)

    assert settings.database_url == STRONG_URL


@pytest.mark.unit
def test_strong_password_no_warning_without_flag(monkeypatch, recwarn):
    monkeypatch.delenv("REQUIRE_SECURE_DB_CREDENTIALS", raising=False)

    settings = Settings(database_url=STRONG_URL)

    assert settings.database_url == STRONG_URL
    assert not [w for w in recwarn.list if issubclass(w.category, SecurityWarning)]
