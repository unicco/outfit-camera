import json

from app.services.environment import CalendarService
from app.settings import Settings


class DummyCredentials:
    called_with: dict[str, object] | None = None

    @classmethod
    def from_service_account_info(cls, info, **kwargs):  # type: ignore[no-untyped-def]
        cls.called_with = {"info": info, **kwargs}
        return "dummy-credentials"


def _make_settings(delegated_user: str | None) -> Settings:
    return Settings(
        database_mode="fallback",
        google_credentials_file=json.dumps({"project_id": "demo"}),
        google_calendar_primary_id="primary",
        google_calendar_delegated_user=delegated_user,
    )


def test_calendar_service_loads_credentials_without_delegation():
    settings = _make_settings(delegated_user=None)
    service = CalendarService(settings)

    credentials = service._load_credentials(DummyCredentials)  # type: ignore[arg-type]

    assert credentials == "dummy-credentials"
    assert DummyCredentials.called_with is not None
    assert DummyCredentials.called_with.get("scopes") == [
        "https://www.googleapis.com/auth/calendar.readonly"
    ]
    assert "subject" not in DummyCredentials.called_with


def test_calendar_service_loads_credentials_with_delegation():
    delegated_email = "delegated@example.com"
    settings = _make_settings(delegated_user=delegated_email)
    service = CalendarService(settings)

    credentials = service._load_credentials(DummyCredentials)  # type: ignore[arg-type]

    assert credentials == "dummy-credentials"
    assert DummyCredentials.called_with is not None
    assert DummyCredentials.called_with.get("subject") == delegated_email
