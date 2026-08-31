"""Pytest configuration and shared fixtures for backend integration tests."""

from __future__ import annotations

import os
import sys
from typing import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

# 路径設定: app モジュールをインポートできるように
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db
from app.models import Base


DATABASE_URL = os.getenv("DATABASE_TEST_URL")
TEST_SCHEMA = "test_integration"

INTEGRATION_DB_UNAVAILABLE = not DATABASE_URL or not DATABASE_URL.startswith("postgresql")

if INTEGRATION_DB_UNAVAILABLE:
    pytest.skip(
        "DATABASE_TEST_URL が未設定のため、バックエンド統合テストをスキップします。",
        allow_module_level=True,
    )


@pytest.fixture(scope="session")
def test_engine():
    """Initialise a PostgreSQL engine and ensure a clean schema for tests."""
    if INTEGRATION_DB_UNAVAILABLE:
        pytest.skip(
            "DATABASE_TEST_URL が未設定のため、バックエンド統合テストをスキップします。",
            allow_module_level=True,
        )

    engine = create_engine(
        DATABASE_URL,
        future=True,
        pool_pre_ping=True,
        connect_args={"options": f"-c search_path={TEST_SCHEMA}"},
    )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:  # pragma: no cover - depends on env setup
        raise RuntimeError(
            f"Failed to connect to PostgreSQL database at {DATABASE_URL}: {exc}"
        ) from exc

    # Clean schema before tests (drop & recreate dedicated test schema)
    with engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))
        connection.execute(text(f"CREATE SCHEMA {TEST_SCHEMA}"))
        Base.metadata.create_all(bind=connection)

    yield engine

    # Drop schema after tests to leave a clean slate
    with engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))

    engine.dispose()


@pytest.fixture()
def db_session(test_engine) -> Generator[Session, None, None]:
    """Provide a SQLAlchemy session bound to the PostgreSQL engine."""
    SessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db_session):
    """Create a FastAPI TestClient with the database dependency overridden."""
    from fastapi.testclient import TestClient

    from app.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
