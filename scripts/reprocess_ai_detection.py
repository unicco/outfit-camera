#!/usr/bin/env python3
"""Script to reprocess existing photos with AI detection and save wardrobe matching results.
This is for Issue #815: Persist AI matching results to database.
"""

# ruff: noqa: E402

import sys
import os
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "api"))
sys.path.insert(0, str(project_root / "src"))

# Set PYTHONPATH environment variable
os.environ["PYTHONPATH"] = str(project_root / "src")

from app.database import get_db
from app.models import Photo, OutfitRecord
from app.ai_detection_api_v2 import ClothingDetectorV2
from app.utils.timezone_utils import jst_now

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def reprocess_photos(date_str: str = None, days_back: int = 7, force: bool = False):
    """Reprocess photos with AI detection to save wardrobe matching results.

    Args:
        date_str: Specific date to reprocess (YYYY-MM-DD format)
        days_back: Number of days to go back from today (default: 7)
        force: Force reprocessing even if outfit records already exist

    """
    db = next(get_db())

    try:
        # Determine date range
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_date = target_date
            end_date = target_date + timedelta(days=1)
            logger.info(f"Processing photos for specific date: {target_date}")
        else:
            end_date = jst_now().date() + timedelta(days=1)
            start_date = end_date - timedelta(days=days_back)
            logger.info(f"Processing photos from {start_date} to {end_date}")

        # Query photos in date range
        photos_query = db.query(Photo).filter(
            Photo.captured_at >= start_date, Photo.captured_at < end_date
        )

        if not force:
            # Exclude photos that already have outfit records
            existing_photo_ids = db.query(OutfitRecord.photo_id).distinct()
            photos_query = photos_query.filter(~Photo.id.in_(existing_photo_ids))

        photos = photos_query.order_by(Photo.captured_at.desc()).all()

        logger.info(f"Found {len(photos)} photos to process")

        detector = ClothingDetectorV2()

        # Process each photo
        success_count = 0
        error_count = 0

        for i, photo in enumerate(photos):
            logger.info(
                f"\n[{i+1}/{len(photos)}] Processing photo {photo.id} "
                f"from {photo.captured_at}"
            )

            try:
                result = detector.process_photo(photo.id, db, apply_wb_correction=True)

                detected_count = len(result.detected_items)
                matched_categories = sum(
                    len(matches) for matches in result.wardrobe_matches.values()
                )

                logger.info(
                    f"✅ Detection successful: {detected_count} items detected, "
                    f"{matched_categories} wardrobe matches"
                )
                success_count += 1

            except Exception as e:
                logger.error(f"❌ Error processing photo {photo.id}: {e}")
                error_count += 1
                continue

        logger.info(f"\n{'='*50}")
        logger.info("Reprocessing complete!")
        logger.info(f"Total photos processed: {len(photos)}")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Errors: {error_count}")
        logger.info(f"{'='*50}")

    except Exception as e:
        logger.error(f"Fatal error during reprocessing: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Reprocess photos with AI detection to save wardrobe matching results"
    )
    parser.add_argument("--date", help="Specific date to process (YYYY-MM-DD format)")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to go back from today (default: 7)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing even if outfit records already exist",
    )

    args = parser.parse_args()

    # Validate date format
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            logger.error("Invalid date format. Please use YYYY-MM-DD")
            return 1

    # Run reprocessing
    reprocess_photos(date_str=args.date, days_back=args.days, force=args.force)

    return 0


if __name__ == "__main__":
    sys.exit(main())
