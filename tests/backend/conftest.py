"""Backend test configuration and fixtures."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Add project directories to Python path
PROJECT_ROOT = Path(__file__).parent.parent.parent
# Ensure src and api modules are importable for backend tests
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "api"))
sys.path.insert(0, str(PROJECT_ROOT))

# Set test environment variables
test_db_url = os.getenv("DATABASE_TEST_URL")
if test_db_url:
    if test_db_url.startswith("sqlite:///"):
        db_path = Path(test_db_url.replace("sqlite:///", ""))
        if db_path.exists():
            db_path.unlink()
    engine = None
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(test_db_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        os.environ["DATABASE_URL"] = test_db_url
    except Exception as exc:  # pragma: no cover - best effort fallback
        print(
            f"⚠️ DATABASE_TEST_URL unreachable ({exc}); falling back to sqlite:///test.db"
        )
        os.environ["DATABASE_URL"] = "sqlite:///test.db"
    finally:
        if engine is not None:
            engine.dispose()
else:
    os.environ["DATABASE_URL"] = "sqlite:///test.db"
    db_path = Path("test.db")
    if db_path.exists():
        db_path.unlink()
os.environ["STORAGE_TYPE"] = "filesystem"
os.environ["DB_ENABLED"] = "true"
# WARDROBE_ENABLED は削除（常に有効）
os.environ["PHOTOS_BASE_DIR"] = "/tmp/test-photos"
os.environ["PHOTOS_LOG_DIR"] = "/tmp/test-logs"
os.environ["DATA_BACKUP_DIR"] = "/tmp/test-data"


@pytest.fixture
def client():
    """Create test client for main.py."""
    from app.main import app

    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _create_test_tables():
    """Ensure SQLite tables exist before tests access endpoints."""
    from app.database import create_tables

    create_tables()
    yield


@pytest.fixture
def client_v2():
    """Create test client for main.py (v2)."""
    from app.main import app

    return TestClient(app)


def pytest_configure(config):
    """Ensure custom markers are registered even when pytest.ini is not discovered."""
    for marker, description in (
        ("unit", "marks tests as unit tests"),
        ("integration", "marks tests as integration tests"),
        ("slow", "marks tests as slow tests"),
        ("performance", "marks tests as performance tests"),
        ("e2e", "marks tests as end-to-end tests"),
        ("manual", "marks tests requiring manual or external setup"),
    ):
        config.addinivalue_line("markers", f"{marker}: {description}")


@pytest.fixture
def mock_db_enabled():
    """Mock database enabled environment."""
    with patch.dict(os.environ, {"DB_ENABLED": "true"}):
        yield


# mock_wardrobe_enabled フィクスチャは削除（ワードローブは常に有効）


def pytest_collection_modifyitems(config, items):
    """Auto-apply markers based on folder location.

    - tests/backend/unit -> @pytest.mark.unit
    - tests/backend/integration -> @pytest.mark.integration
    - tests/backend/performance -> @pytest.mark.slow
    """
    for item in items:
        path = Path(str(getattr(item, "fspath", "")))
        pstr = str(path)
        if "/tests/backend/unit/" in pstr or pstr.endswith("/tests/backend/unit"):
            item.add_marker(pytest.mark.unit)
        elif "/tests/backend/integration/" in pstr:
            item.add_marker(pytest.mark.integration)
        elif "/tests/backend/performance/" in pstr:
            item.add_marker(pytest.mark.slow)
