"""Tests for new /api prefixed endpoints."""

import uuid
from datetime import date

from fastapi.testclient import TestClient


def test_daily_reset(client: TestClient):
    """Test POST /api/v2/daily-reset endpoint."""
    response = client.post("/api/v2/daily-reset")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "reset" in response.json()["message"].lower()


def test_capture_required(client: TestClient):
    """Test GET /api/v2/capture-required endpoint."""
    response = client.get("/api/v2/capture-required")
    assert response.status_code == 200

    data = response.json()
    assert "capture_required" in data
    assert "already_captured" in data
    assert "capture_count_today" in data
    assert "message" in data

    # capture_required and already_captured should be opposite
    assert data["capture_required"] != data["already_captured"]


def test_get_photo(client: TestClient):
    """Test GET /api/v2/photo/{photo_id} endpoint."""
    # Test with non-existent photo
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/v2/photo/{fake_id}")
    assert response.status_code == 404
    payload = response.json()
    assert payload.get("error") == "Not Found"
    assert "not found" in payload.get("message", "").lower()


def test_get_photo_binary(client: TestClient):
    """Test GET /api/v2/photos/{photo_id} endpoint."""
    # Test with non-existent photo
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/v2/photos/{fake_id}")
    assert response.status_code == 404
    payload = response.json()
    assert payload.get("error") == "Not Found"
    assert "not found" in payload.get("message", "").lower()


def test_get_dates(client: TestClient):
    """Test GET /api/v2/dates endpoint."""
    response = client.get("/api/v2/dates")
    assert response.status_code == 200

    dates = response.json()
    assert isinstance(dates, list)

    # If there are dates, they should be in reverse chronological order
    if len(dates) > 1:
        if isinstance(dates[0], dict) and "date" in dates[0]:
            for i in range(len(dates) - 1):
                assert dates[i]["date"] >= dates[i + 1]["date"]
        else:
            for i in range(len(dates) - 1):
                assert dates[i] >= dates[i + 1]


def test_get_records_by_clothing(client: TestClient):
    """Test GET /api/v2/records/by-clothing/{clothing_item} endpoint."""
    # Test with a common clothing item
    response = client.get("/api/v2/records/by-clothing/シャツ")
    assert response.status_code == 200

    records = response.json()
    assert isinstance(records, list)

    # If there are records, each should have the clothing item
    for record in records:
        assert "clothing_items" in record
        assert "シャツ" in record["clothing_items"]


def test_delete_no_person_records(client: TestClient):
    """Test DELETE /api/v2/records/no-person endpoint."""
    response = client.delete("/api/v2/records/no-person")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert "deleted_count" in data
    assert isinstance(data["deleted_count"], int)
    assert data["deleted_count"] >= 0


def test_get_records_with_date_filter(client: TestClient):
    """Test GET /api/v2/records with date filter."""
    today = date.today().isoformat()
    response = client.get(f"/api/v2/records?date_filter={today}")
    assert response.status_code == 200

    records = response.json()
    assert isinstance(records, list)

    # All records should be from the specified date
    for record in records:
        assert record["date"] == today


def test_daily_status(client: TestClient):
    """Test GET /api/v2/daily-status endpoint."""
    response = client.get("/api/v2/daily-status")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "history" in data
    assert "version" in data

    status = data["status"]
    assert "date" in status
    assert "captured_today" in status
    assert "capture_count" in status
    assert "storage_stats" in status
