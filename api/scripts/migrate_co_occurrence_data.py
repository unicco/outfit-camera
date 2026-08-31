#!/usr/bin/env python
"""Script to migrate existing outfit data to co-occurrence tables."""

import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app.co_occurrence_batch import CoOccurrenceBatchProcessor
from app.co_occurrence_models import Base as CoOccurrenceBase

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Run the migration."""
    logger.info("Starting co-occurrence data migration...")

    # Create tables if they don't exist
    CoOccurrenceBase.metadata.create_all(bind=engine)
    logger.info("Co-occurrence tables created/verified")

    # Create session
    db: Session = SessionLocal()

    try:
        # Create batch processor
        batch_processor = CoOccurrenceBatchProcessor(db)

        # Run migration
        batch_processor.migrate_existing_data()

        logger.info("Migration completed successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
