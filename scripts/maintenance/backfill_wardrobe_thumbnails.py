#!/usr/bin/env python3
"""Backfill wardrobe thumbnails for existing items (Issue #1132).

This script scans clothing_items.image_metadata.
If thumbnails (thumb_200/thumb_400) are missing for a wardrobe image,
it regenerates and uploads them to Google Cloud Storage and updates the
metadata accordingly. Designed to be idempotent and safe to re-run.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
import copy
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from google.api_core import exceptions as gcs_exceptions
from google.cloud import storage
from PIL import ImageFile

# Ensure project packages are importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Allow PIL to read truncated image streams instead of raising an exception
ImageFile.LOAD_TRUNCATED_IMAGES = True
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "api"))
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables early
try:
    from dotenv import load_dotenv

    env_common = PROJECT_ROOT / ".env.common"
    if env_common.exists():
        load_dotenv(env_common)
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
except ImportError:
    pass

from app.database import SessionLocal  # noqa: E402
from app.image_upload_service import ImageUploadService  # noqa: E402
from app.utils.timezone_utils import TimezoneUtils  # noqa: E402
from app.wardrobe_models import ClothingItem  # noqa: E402

TARGET_SIZES: tuple[int, int] = (200, 400)
LOGGER = logging.getLogger("thumb-backfill")


@dataclass
class BackfillStats:
    processed_items: int = 0
    updated_items: int = 0
    regenerated_thumbnails: int = 0
    skipped_items: int = 0
    failed_items: int = 0
    normalized_items: int = 0


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="[%(levelname)s] %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill wardrobe thumbnails in GCS",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate changes without writing to GCS or the database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most this many clothing items.",
    )
    parser.add_argument(
        "--item-id",
        action="append",
        dest="item_ids",
        help="Specify clothing item ID(s) to target (can be repeated).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between processed items (rate limiting).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retries per thumbnail upload (default: 2).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args()


def _parse_blob_name_from_url(url: str, bucket_name: str) -> Optional[str]:
    if not url:
        return None

    parsed = urlparse(url)
    if parsed.netloc != "storage.googleapis.com":
        return None

    path = parsed.path.lstrip("/")
    if not path:
        return None

    parts = path.split("/", 1)
    if len(parts) != 2:
        return None

    url_bucket, blob_path = parts
    if url_bucket != bucket_name:
        return None

    return blob_path


def _ensure_thumbnail_dict(image_entry: dict[str, Any]) -> dict[str, Any]:
    thumbnails = image_entry.get("thumbnails")
    if isinstance(thumbnails, dict):
        return thumbnails

    thumbnails_dict: dict[str, Any] = {}
    image_entry["thumbnails"] = thumbnails_dict
    return thumbnails_dict


def _primary_image_url_payload(
    images: Iterable[dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for image in images:
        if not isinstance(image, dict):
            continue
        original = image.get("original_url")
        thumbnails = image.get("thumbnails")
        if not original and not isinstance(thumbnails, dict):
            continue
        thumb_payload: Dict[str, str] = {}
        if isinstance(thumbnails, dict):
            thumb_payload = {
                key: value
                for key, value in thumbnails.items()
                if isinstance(key, str) and isinstance(value, str) and value
            }
        if original or thumb_payload:
            return {
                "original": original,
                "thumbnails": thumb_payload,
            }
    return None


def _download_original_bytes(
    storage_client: storage.Client,
    bucket_name: str,
    blob_name: str,
) -> bytes:
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if not blob.exists():
        raise FileNotFoundError(f"Blob not found: gs://{bucket_name}/{blob_name}")
    return blob.download_as_bytes()


def _upload_thumbnail(
    service: ImageUploadService,
    item_id: str,
    image_id: str,
    size: int,
    thumbnail_bytes: bytes,
) -> str:
    blob_name = f"wardrobe/{item_id}/{image_id}_thumb_{size}.jpg"
    blob = service.bucket.blob(blob_name)
    blob.upload_from_string(thumbnail_bytes, content_type="image/jpeg")
    return blob.public_url


def _regenerate_thumbnails_for_image(
    service: ImageUploadService,
    storage_client: storage.Client,
    bucket_name: str,
    item: ClothingItem,
    image_entry: dict[str, Any],
    missing_sizes: List[int],
    retries: int,
) -> Dict[int, str]:
    image_id = image_entry.get("id")
    original_url = image_entry.get("original_url")

    if not image_id or not isinstance(image_id, str):
        raise ValueError("Image metadata entry missing 'id'")
    if not original_url or not isinstance(original_url, str):
        raise ValueError("Image metadata entry missing 'original_url'")

    blob_name = _parse_blob_name_from_url(original_url, bucket_name)
    if not blob_name:
        raise ValueError(
            f"Unsupported original URL for thumbnail backfill: {original_url}"
        )

    original_bytes = _download_original_bytes(storage_client, bucket_name, blob_name)

    generated_urls: Dict[int, str] = {}
    for size in missing_sizes:
        attempt = 0
        last_error: Optional[Exception] = None
        while attempt <= retries:
            try:
                thumb_bytes = service._generate_thumbnail(
                    original_bytes, size
                )  # noqa: SLF001
                thumb_url = _upload_thumbnail(
                    service, str(item.id), image_id, size, thumb_bytes
                )
                generated_urls[size] = thumb_url
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempt += 1
                time.sleep(min(1, 0.2 * attempt))
        if size not in generated_urls and last_error:
            raise last_error

    return generated_urls


def _sanitize_image_entry(
    entry: dict[str, Any],
    bucket_name: str,
) -> Optional[dict[str, Any]]:
    if not isinstance(entry, dict):
        return None

    original_url = entry.get("original_url")
    image_id = entry.get("id")

    if not isinstance(original_url, str):
        return None

    # Ensure the URL points to the current bucket to avoid cross-environment leakage
    blob_path = _parse_blob_name_from_url(original_url, bucket_name)
    if not blob_path:
        LOGGER.debug("Skipping image with unsupported URL: %s", original_url)
        return None

    if not image_id:
        filename = os.path.basename(blob_path)
        image_id = os.path.splitext(filename)[0]

    thumbnails = (
        entry.get("thumbnails") if isinstance(entry.get("thumbnails"), dict) else {}
    )

    sanitized = {
        "id": str(image_id),
        "original_url": original_url,
        "thumbnails": {
            key: value
            for key, value in thumbnails.items()
            if isinstance(key, str) and isinstance(value, str) and value
        },
    }

    # Preserve optional metadata when available
    if entry.get("size") is not None:
        sanitized["size"] = entry["size"]
    if entry.get("content_type") is not None:
        sanitized["content_type"] = entry["content_type"]
    if entry.get("filename") is not None:
        sanitized["filename"] = entry["filename"]

    return sanitized


def _build_entry_from_url(url: str, bucket_name: str) -> Optional[dict[str, Any]]:
    if not isinstance(url, str):
        return None

    blob_path = _parse_blob_name_from_url(url, bucket_name)
    if not blob_path:
        LOGGER.debug("Skipping URL outside target bucket: %s", url)
        return None

    filename = os.path.basename(blob_path)
    file_id, _sep, _ext = filename.partition(".")
    if not file_id:
        return None

    return {
        "id": file_id,
        "original_url": url,
        "thumbnails": {},
        "filename": filename,
    }


def _entries_from_image_urls(
    image_urls: Any,
    bucket_name: str,
) -> Tuple[List[dict[str, Any]], bool]:
    """Extract image entries from legacy image_urls formats.

    Returns a tuple of (entries, normalization_needed).
    """
    entries: List[dict[str, Any]] = []
    normalization_needed = False

    if isinstance(image_urls, dict):
        original = image_urls.get("original")
        thumbnails = image_urls.get("thumbnails")
        entry = _build_entry_from_url(original, bucket_name)
        if entry:
            if isinstance(thumbnails, dict):
                entry["thumbnails"].update(
                    {
                        key: value
                        for key, value in thumbnails.items()
                        if isinstance(key, str) and isinstance(value, str) and value
                    }
                )
            entries.append(entry)
        # No normalization required if already dict-based with thumbnails
        normalization_needed = not (
            isinstance(image_urls.get("thumbnails"), dict) and isinstance(original, str)
        )

    elif isinstance(image_urls, list):
        normalization_needed = True
        for url in image_urls:
            entry = _build_entry_from_url(url, bucket_name)
            if entry:
                entries.append(entry)

    elif isinstance(image_urls, str):
        normalization_needed = True
        entry = _build_entry_from_url(image_urls, bucket_name)
        if entry:
            entries.append(entry)

    return entries, normalization_needed


def _collect_canonical_images(
    item: ClothingItem,
    bucket_name: str,
) -> Tuple[List[dict[str, Any]], bool]:
    """Merge image information from metadata and legacy image_urls."""
    normalization_needed = False
    images_by_id: Dict[str, dict[str, Any]] = {}

    metadata = item.image_metadata if isinstance(item.image_metadata, dict) else {}
    raw_images = metadata.get("images") if isinstance(metadata, dict) else None

    if isinstance(raw_images, list):
        for entry in raw_images:
            sanitized = _sanitize_image_entry(entry, bucket_name)
            if sanitized and sanitized["id"]:
                images_by_id[sanitized["id"]] = sanitized

    legacy_entries, legacy_normalization = _entries_from_image_urls(
        item.image_urls,
        bucket_name,
    )
    normalization_needed = normalization_needed or legacy_normalization

    for entry in legacy_entries:
        image_id = entry["id"]
        existing = images_by_id.get(image_id)
        if existing:
            if entry.get("original_url") and existing.get("original_url") != entry.get(
                "original_url"
            ):
                existing["original_url"] = entry["original_url"]
                normalization_needed = True
            if entry.get("filename") and not existing.get("filename"):
                existing["filename"] = entry["filename"]
            incoming_thumbs = entry.get("thumbnails", {})
            if incoming_thumbs:
                thumbnails = _ensure_thumbnail_dict(existing)
                for key, value in incoming_thumbs.items():
                    if thumbnails.get(key) != value:
                        thumbnails[key] = value
                        normalization_needed = True
        else:
            images_by_id[image_id] = entry
            normalization_needed = True

    canonical_images = list(images_by_id.values())
    return canonical_images, normalization_needed


def _clone_metadata(metadata: Any) -> dict[str, Any]:
    if isinstance(metadata, dict):
        return copy.deepcopy(metadata)
    return {}


def process_item(
    item: ClothingItem,
    service: ImageUploadService,
    storage_client: storage.Client,
    bucket_name: str,
    dry_run: bool,
    retries: int,
) -> Dict[str, Any]:
    canonical_images, normalization_needed = _collect_canonical_images(
        item,
        bucket_name,
    )

    if not canonical_images:
        LOGGER.debug("Item %s has no valid images to process", item.id)
        return {"updated": False, "generated": 0, "normalized": False}

    working_images = [copy.deepcopy(image) for image in canonical_images]

    generated_total = 0
    thumbnails_updated = False

    for image_entry in working_images:
        thumbnails = _ensure_thumbnail_dict(image_entry)
        missing_sizes = [
            size
            for size in TARGET_SIZES
            if not isinstance(thumbnails.get(f"thumb_{size}"), str)
        ]

        if not missing_sizes:
            continue

        LOGGER.info(
            "Item %s image %s missing thumbnails %s",
            item.id,
            image_entry.get("id"),
            missing_sizes,
        )

        if dry_run:
            generated_total += len(missing_sizes)
            continue

        generated_urls = _regenerate_thumbnails_for_image(
            service,
            storage_client,
            bucket_name,
            item,
            image_entry,
            missing_sizes,
            retries,
        )
        for size, url in generated_urls.items():
            thumbnails[f"thumb_{size}"] = url
        generated_total += len(generated_urls)
        thumbnails_updated = True

    metadata_changed = normalization_needed or thumbnails_updated

    if dry_run:
        return {
            "updated": False,
            "generated": generated_total,
            "normalized": metadata_changed,
        }

    if not metadata_changed:
        return {"updated": False, "generated": 0, "normalized": False}

    metadata = _clone_metadata(item.image_metadata)
    metadata["images"] = working_images
    metadata["updated_at"] = TimezoneUtils.now_jst().isoformat()
    item.image_metadata = metadata

    primary_payload = _primary_image_url_payload(working_images)
    if primary_payload:
        item.image_urls = primary_payload

    return {"updated": True, "generated": generated_total, "normalized": True}


def main() -> None:
    args = parse_args()
    _configure_logging(args.verbose)

    LOGGER.info("Starting wardrobe thumbnail backfill (dry_run=%s)", args.dry_run)

    service = ImageUploadService()
    storage_client = service.client if hasattr(service, "client") else storage.Client()
    bucket_name = service.bucket_name

    stats = BackfillStats()
    session = SessionLocal()

    try:
        query = session.query(ClothingItem)
        if args.item_ids:
            query = query.filter(ClothingItem.id.in_(args.item_ids))
        query = query.order_by(ClothingItem.created_at)

        count = 0
        for item in query:
            if args.limit is not None and count >= args.limit:
                break

            stats.processed_items += 1
            count += 1

            try:
                result = process_item(
                    item,
                    service,
                    storage_client,
                    bucket_name,
                    dry_run=args.dry_run,
                    retries=args.retries,
                )
            except (
                gcs_exceptions.GoogleAPIError,
                FileNotFoundError,
                ValueError,
                OSError,
            ) as error:
                if not args.dry_run:
                    session.rollback()
                stats.failed_items += 1
                LOGGER.error("Failed to process item %s: %s", item.id, error)
                continue

            generated = result.get("generated", 0)
            updated = result.get("updated", False)
            normalized = result.get("normalized", False)

            if generated:
                stats.regenerated_thumbnails += generated
            if updated:
                stats.updated_items += 1
            if normalized:
                stats.normalized_items += 1
            elif not generated:
                stats.skipped_items += 1

            if updated and not args.dry_run:
                session.add(item)
                session.commit()
            elif args.dry_run and generated:
                LOGGER.debug(
                    "Dry run: item %s would update %s thumbnails",
                    item.id,
                    generated,
                )

            if args.sleep:
                time.sleep(args.sleep)

        if args.dry_run:
            LOGGER.info("Dry run complete - no database changes committed")

    finally:
        session.close()

    LOGGER.info("=== Backfill summary ===")
    LOGGER.info("Processed items: %s", stats.processed_items)
    LOGGER.info("Updated items:   %s", stats.updated_items)
    LOGGER.info("Skipped items:   %s", stats.skipped_items)
    LOGGER.info("Failed items:    %s", stats.failed_items)
    LOGGER.info("Generated thumbs: %s", stats.regenerated_thumbnails)
    LOGGER.info("Normalized items: %s", stats.normalized_items)


if __name__ == "__main__":
    main()
