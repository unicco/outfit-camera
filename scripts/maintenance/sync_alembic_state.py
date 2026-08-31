#!/usr/bin/env python3
"""Synchronize the production database with the Alembic head revision.

This script performs two actions:
1. Drops the legacy photos.ai_annotation_image_url column if it still exists.
2. Stamps the database's alembic_version table to the latest Alembic head.

Run this after loading project environment variables so DATABASE_URL is set.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

TARGET_REVISION = "f8c4d5e6a7b9"
LEGACY_COLUMN_SQL = (
    "ALTER TABLE IF EXISTS photos "
    "DROP COLUMN IF EXISTS ai_annotation_image_url"
)


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable must be set.")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(LEGACY_COLUMN_SQL))

    repo_root = Path(__file__).resolve().parents[2]
    api_path = repo_root / "api"
    sys.path.insert(0, str(api_path))
    alembic_config_path = repo_root / "api" / "alembic.ini"
    alembic_cfg = Config(str(alembic_config_path))
    alembic_cfg.set_main_option("script_location", str(api_path / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    command.stamp(alembic_cfg, TARGET_REVISION)


if __name__ == "__main__":
    main()
