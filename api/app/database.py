"""Simplified database configuration for single-table design."""

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import DAILY_SUMMARY_VIEW, Base
from .settings import get_settings
from .wardrobe_models import Base as WardrobeBase

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    # First load .env.common for shared settings
    env_common_path = Path(__file__).parent.parent.parent / ".env.common"
    if env_common_path.exists():
        load_dotenv(env_common_path)

    # Then load .env to override with session-specific settings
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path, override=True)
except ImportError:
    pass


# Database configuration
def _normalize_database_url(url: str) -> str:
    """Align SQLAlchemy driver prefix with installed client libraries."""
    if url.startswith("postgresql://"):
        try:
            import importlib.util

            if importlib.util.find_spec("psycopg") is not None:
                return url.replace("postgresql://", "postgresql+psycopg://", 1)
        except ImportError:
            pass
    return url


DATABASE_URL = _normalize_database_url(
    os.getenv(
        "DATABASE_URL",
        "sqlite:///./coordinate_recorder.db",
    )
)


# Create engine with connection pooling
_db_echo = get_settings().db_echo
if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=_db_echo,
    )
else:
    # SQLite configuration
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=_db_echo,
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables() -> None:
    """Create all database tables and views."""
    # Import here to avoid circular imports during module initialization.
    # external_rental_models / co_occurrence_models must be imported so their
    # tables register on Base.metadata before create_all resolves the FK from
    # outfit_external_rental_items -> external_rental_items (NoReferencedTableError otherwise).
    from . import co_occurrence_models, external_rental_models  # noqa: F401
    from .search_log_models import Base as SearchLogBase

    # Create tables from all Base classes
    Base.metadata.create_all(bind=engine)
    WardrobeBase.metadata.create_all(bind=engine)
    SearchLogBase.metadata.create_all(bind=engine)

    # Create views for PostgreSQL
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text(DAILY_SUMMARY_VIEW))
            conn.commit()


def drop_old_tables() -> None:
    """Drop old tables that are no longer needed."""
    with engine.connect() as conn:
        # Drop old tables if they exist
        old_tables = ["app_settings", "system_logs", "outfit_records", "daily_captures"]

        for table in old_tables:
            # Use SQLAlchemy identifier to safely quote table names
            from sqlalchemy import inspect

            inspector = inspect(conn)
            if table in inspector.get_table_names():
                quoted_table = conn.dialect.identifier_preparer.quote(table)
                if DATABASE_URL.startswith("postgresql"):
                    conn.execute(text(f"DROP TABLE IF EXISTS {quoted_table} CASCADE"))
                else:
                    conn.execute(text(f"DROP TABLE IF EXISTS {quoted_table}"))

        conn.commit()


def get_db() -> Generator[Session, None, None]:
    """Dependency function to get database session.

    Yields:
        Database session

    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_engine() -> Engine:
    """Get the database engine."""
    return engine


def check_database_connection() -> bool:
    """Check if database connection is healthy.

    Returns:
        True if connection is successful, False otherwise

    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
