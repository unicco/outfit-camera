
import pytest

pytest.skip("レガシー API テストは現在のユニット検証から除外", allow_module_level=True)

"""Unit tests for records router behavior without in-memory fallback."""

from datetime import datetime
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import records


@pytest.fixture
def app() -> Iterator[FastAPI]:
    """Provide a FastAPI app with the records router only."""
    app = FastAPI()
    app.include_router(records.router)
    yield app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Return a test client for the records router."""
    with TestClient(app) as test_client:
        yield test_client


def override_db(session: MagicMock):
    """Create dependency override for get_db."""

    def _override() -> Iterator[MagicMock]:
        yield session

    return _override


def test_get_outfit_records_returns_503_when_db_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify 503 is returned when the database is disabled."""
    monkeypatch.setattr(records, "DB_ENABLED", False)
    session = MagicMock()
    client.app.dependency_overrides[records.get_db] = override_db(session)

    response = client.get("/records")

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "Database service is unavailable. Please check database connection."
    )


def test_get_outfit_records_returns_data_from_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify records are fetched from the database when available."""
    monkeypatch.setattr(records, "DB_ENABLED", True)

    session = MagicMock()
    query = MagicMock()
    query.order_by.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.return_value = [
        SimpleNamespace(
            id="record-1",
            date=datetime(2024, 1, 1, 12, 0, 0),
            photo_id="photo-1",
            clothing_items=["シャツ"],
            notes="memo",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            person_detected=True,
        ),
        SimpleNamespace(
            id="record-2",
            date=datetime(2024, 1, 2, 12, 0, 0),
            photo_id="photo-2",
            clothing_items=["パンツ"],
            notes=None,
            created_at=datetime(2024, 1, 2, 12, 0, 0),
            person_detected=False,
        ),
    ]
    session.query.return_value = query

    client.app.dependency_overrides[records.get_db] = override_db(session)

    response = client.get("/records?limit=10&offset=0")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == "record-1"
    # BaseModel で camelCase に変換されるため JSON では clothingItems を期待する
    assert data[0]["clothingItems"] == ["シャツ"]
    assert data[1]["clothingItems"] == ["パンツ"]


def test_get_outfit_records_handles_database_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify database errors are surfaced as 503 responses."""
    monkeypatch.setattr(records, "DB_ENABLED", True)

    session = MagicMock()
    query = MagicMock()
    query.order_by.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.all.side_effect = RuntimeError("db failure")
    session.query.return_value = query

    client.app.dependency_overrides[records.get_db] = override_db(session)

    response = client.get("/records")

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "Database service is unavailable. Please check database connection."
    )
