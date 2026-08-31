"""Tests for external rental API endpoints."""

from __future__ import annotations

import importlib
import os
from datetime import datetime
from typing import Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

os.environ.setdefault("DATABASE_TEST_URL", "sqlite:///test.db")
os.environ["DATABASE_URL"] = os.environ["DATABASE_TEST_URL"]

import app.database as database_module

database_module = importlib.reload(database_module)
sqlite_url = database_module._normalize_database_url(os.environ["DATABASE_TEST_URL"])
database_module.DATABASE_URL = sqlite_url
try:
    database_module.engine.dispose()
except Exception:
    pass
database_module.engine = create_engine(
    sqlite_url,
    connect_args={"check_same_thread": False},
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
)
database_module.SessionLocal.configure(bind=database_module.engine)
SessionLocal = database_module.SessionLocal
from app.external_rental_models import ExternalRentalItem


@pytest.fixture(autouse=True)
def _cleanup_external_rentals() -> Generator[None, None, None]:
    """Ensure external_rental_items table is cleared between tests."""
    session = SessionLocal()
    try:
        dialect_name = session.bind.dialect.name
        if dialect_name == "sqlite":
            # SQLite (unit tests) does not support `ADD COLUMN IF NOT EXISTS`,
            # so check the table schema manually before altering.
            existing_columns = {
                row[1]
                for row in session.execute(
                    text("PRAGMA table_info(external_rental_items)")
                )
            }
            if "image_url" not in existing_columns:
                session.execute(
                    text(
                        "ALTER TABLE external_rental_items "
                        "ADD COLUMN image_url VARCHAR(500)"
                    )
                )
        session.query(ExternalRentalItem).delete()
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        session.query(ExternalRentalItem).delete()
        session.commit()
    finally:
        session.close()


def test_import_and_summary_for_example_rental(client_v2) -> None:
    payload = {
        "capturedAt": "2025-02-04T09:00:00+09:00",
        "items": [
            {
                "brand": "AURALEE",
                "itemName": "Super Fine Wool Coat",
                "size": "M",
                "managementNumber": "AA-12345",
                "returnDueDate": "2025/02/20",
                "rawAttributes": {"section": "レンタル中のアイテム"},
                "imageUrl": "https://example.com/images/coat.jpg",
            },
            {
                "brand": "steven alan",
                "itemName": "Wide Pants",
                "size": "1",
                "managementNumber": "AA-67890",
                "returnDueDate": "2025年02月22日",
                "imageUrl": None,
            },
        ],
    }

    response = client_v2.post(
        "/api/v2/external-rentals/example_rental/import", json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["createdCount"] == 2
    assert data["updatedCount"] == 0
    assert data["returnedCount"] == 0
    assert data["totalActiveItems"] == 2
    assert len(data["items"]) == 2
    # costPerWear is None until wear count is recorded
    assert all(item["costPerWear"] is None for item in data["items"])
    # rentalCost defaults to the monthly plan (¥5,940) on import
    assert all(item["rentalCost"] == pytest.approx(9999.0) for item in data["items"])
    assert data["items"][0]["imageUrl"] == "https://example.com/images/coat.jpg"
    assert data["items"][1]["imageUrl"] is None

    summary = client_v2.get("/api/v2/external-rentals/summary")
    assert summary.status_code == 200
    summary_data = summary.json()
    assert summary_data["planCost"] == pytest.approx(9999.0)
    assert summary_data["activeItemCount"] == 2
    assert summary_data["totalWearCount"] == 0
    assert summary_data["costPerWear"] is None


def test_update_rental_cost_recomputes_cost_per_wear(client_v2) -> None:
    payload = {
        "capturedAt": "2025-02-04T09:00:00+09:00",
        "items": [
            {
                "brand": "AURALEE",
                "itemName": "Super Fine Wool Coat",
                "size": "M",
                "managementNumber": "AA-12345",
            },
        ],
    }
    imported = client_v2.post(
        "/api/v2/external-rentals/example_rental/import", json=payload
    )
    assert imported.status_code == 200
    item = imported.json()["items"][0]
    assert item["rentalCost"] == pytest.approx(9999.0)
    item_id = item["id"]

    # Record 3 wears.
    client_v2.patch(f"/api/v2/external-rentals/{item_id}", json={"incrementWear": 3})

    # Campaign month: user re-allocates this item's cost to ¥2,970.
    patched = client_v2.patch(
        f"/api/v2/external-rentals/{item_id}", json={"rentalCost": 2970}
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["rentalCost"] == pytest.approx(2970.0)
    # ¥2,970 ÷ 3 wears = ¥990
    assert body["costPerWear"] == pytest.approx(990.0)

    summary = client_v2.get("/api/v2/external-rentals/summary").json()
    assert summary["costPerWear"] == pytest.approx(990.0)


def test_update_wear_count_and_reimport_marks_returned(client_v2) -> None:
    initial_payload = {
        "capturedAt": datetime(2025, 2, 4, 9, 0, 0).isoformat(),
        "items": [
            {
                "brand": "HYKE",
                "itemName": "Military Coat",
                "size": "2",
                "managementNumber": "AA-13579",
                "returnDueDate": "2025-02-25",
                "imageUrl": "https://example.com/images/military.jpg",
            },
            {
                "brand": "Drawer",
                "itemName": "Silk Blouse",
                "size": "36",
                "managementNumber": "AA-24680",
                "returnDueDate": "2025-02-21",
                "imageUrl": "https://example.com/images/blouse.jpg",
            },
        ],
    }
    first_import = client_v2.post(
        "/api/v2/external-rentals/example_rental/import", json=initial_payload
    )
    assert first_import.status_code == 200
    first_items = first_import.json()["items"]
    assert len(first_items) == 2

    target_item_id = first_items[0]["id"]
    patch_response = client_v2.patch(
        f"/api/v2/external-rentals/{target_item_id}",
        json={"incrementWear": 2},
    )
    assert patch_response.status_code == 200
    patched_item = patch_response.json()
    assert patched_item["wearCount"] == 2
    # Per-item cost-per-wear: rentalCost (¥5,940) ÷ wearCount (2)
    assert patched_item["costPerWear"] == pytest.approx(2970.0)

    summary_after_patch = client_v2.get("/api/v2/external-rentals/summary").json()
    assert summary_after_patch["totalWearCount"] == 2
    # Summary cost-per-wear: Σ rentalCost (9999 + 9999) ÷ Σ wearCount (2)
    assert summary_after_patch["costPerWear"] == pytest.approx(9999.0)

    second_payload = {
        "capturedAt": datetime(2025, 2, 5, 9, 0, 0).isoformat(),
        "items": [
            {
                "brand": "HYKE",
                "itemName": "Military Coat",
                "size": "2",
                "managementNumber": "AA-13579",
                "returnDueDate": "2025-02-26",
            }
        ],
    }
    second_import = client_v2.post(
        "/api/v2/external-rentals/example_rental/import", json=second_payload
    )
    assert second_import.status_code == 200
    second_data = second_import.json()
    assert second_data["createdCount"] == 0
    assert second_data["updatedCount"] == 1
    assert second_data["returnedCount"] == 1
    assert second_data["totalActiveItems"] == 1
    assert len(second_data["items"]) == 1

    summary_after_second = client_v2.get("/api/v2/external-rentals/summary").json()
    assert summary_after_second["activeItemCount"] == 1
    assert summary_after_second["items"][0]["managementNumber"] == "AA-13579"
    assert summary_after_second["items"][0]["imageUrl"] == "https://example.com/images/military.jpg"


def test_invalid_return_due_date_returns_400(client_v2) -> None:
    import_payload = {
        "items": [
            {
                "itemName": "Chunky Knit",
                "managementNumber": "AA-99999",
                "imageUrl": "https://example.com/images/chunky.jpg",
            }
        ]
    }
    import_response = client_v2.post(
        "/api/v2/external-rentals/example_rental/import", json=import_payload
    )
    assert import_response.status_code == 200
    item_id = import_response.json()["items"][0]["id"]

    patch_response = client_v2.patch(
        f"/api/v2/external-rentals/{item_id}",
        json={"returnDueDate": "invalid"},
    )
    assert patch_response.status_code == 400

    summary = client_v2.post(
        "/api/v2/external-rentals/example_rental/import",
        json={
            "items": [
                {
                    "itemName": "Chunky Knit",
                    "managementNumber": "AA-99999",
                    "returnDueDate": "invalid",
                    "imageUrl": "https://example.com/images/chunky.jpg",
                }
            ]
        },
    )
    assert summary.status_code == 400


def test_import_requires_auth_when_enforced(client_v2) -> None:
    with patch.dict(
        os.environ, {"EXTERNAL_RENTAL_AUTH_REQUIRED": "true"}, clear=False
    ):
        response = client_v2.post(
            "/api/v2/external-rentals/example_rental/import",
            json={"items": []},
        )
    assert response.status_code == 401


def test_import_accepts_cloudflare_headers_when_enforced(client_v2) -> None:
    payload = {
        "items": [
            {
                "itemName": "Cloudflare Secured Coat",
                "managementNumber": "AA-CLF-001",
            }
        ]
    }
    headers = {
        "Cf-Access-Authenticated-User-Email": "user@example.com",
        "Cf-Access-Jwt-Assertion": "dummy-token",
    }
    with patch.dict(
        os.environ, {"EXTERNAL_RENTAL_AUTH_REQUIRED": "true"}, clear=False
    ):
        response = client_v2.post(
            "/api/v2/external-rentals/example_rental/import",
            json=payload,
            headers=headers,
        )
    assert response.status_code == 200


def test_summary_requires_auth_when_enforced(client_v2) -> None:
    with patch.dict(
        os.environ, {"EXTERNAL_RENTAL_AUTH_REQUIRED": "true"}, clear=False
    ):
        response = client_v2.get("/api/v2/external-rentals/summary")
    assert response.status_code == 401


def test_import_accepts_bearer_token_when_enforced(client_v2) -> None:
    payload = {
        "items": [
            {
                "itemName": "Token Auth Blouse",
                "managementNumber": "AA-TKN-001",
            }
        ]
    }
    token = "super-secret-token"
    with patch.dict(
        os.environ,
        {
            "EXTERNAL_RENTAL_AUTH_REQUIRED": "true",
            "EXTERNAL_RENTAL_API_TOKEN": token,
        },
        clear=False,
    ):
        response = client_v2.post(
            "/api/v2/external-rentals/example_rental/import",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200


def test_external_rental_endpoints_require_auth_in_production(
    client_v2, monkeypatch
) -> None:
    """Ensure unauthenticated requests are rejected when ENVIRONMENT=production."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("EXTERNAL_RENTAL_AUTH_BYPASS", raising=False)
    monkeypatch.delenv("EXTERNAL_RENTAL_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("EXTERNAL_RENTAL_AUTH_REQUIRED", raising=False)

    response = client_v2.get("/api/v2/external-rentals/summary")
    assert response.status_code == 401


def test_external_rental_endpoints_allow_cloudflare_authenticated_request(
    client_v2, monkeypatch
) -> None:
    """Requests with Cloudflare Access headers should succeed in production."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("EXTERNAL_RENTAL_AUTH_BYPASS", raising=False)
    monkeypatch.delenv("EXTERNAL_RENTAL_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("EXTERNAL_RENTAL_AUTH_REQUIRED", raising=False)

    response = client_v2.get(
        "/api/v2/external-rentals/summary",
        headers={"Cf-Access-Authenticated-User-Email": "tester@example.com"},
    )
    assert response.status_code == 200
