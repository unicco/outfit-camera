"""Tests for wardrobe thumbnail backfill normalization helpers."""

from types import SimpleNamespace

import pytest

from scripts.maintenance import backfill_wardrobe_thumbnails as backfill


@pytest.fixture()
def dummy_service() -> SimpleNamespace:
    """Service stub for process_item."""
    return SimpleNamespace(bucket_name="test-bucket", bucket=None)


def test_process_item_normalizes_legacy_image_urls(
    dummy_service: SimpleNamespace,
) -> None:
    """Legacy array-based image_urls should be converted to dict format."""
    item = SimpleNamespace(
        id="item-123",
        image_metadata={
            "images": [
                {
                    "id": "img-001",
                    "original_url": "https://storage.googleapis.com/test-bucket/wardrobe/item-123/img-001.jpg",
                    "thumbnails": {
                        "thumb_200": "https://storage.googleapis.com/test-bucket/wardrobe/item-123/img-001_thumb_200.jpg",
                        "thumb_400": "https://storage.googleapis.com/test-bucket/wardrobe/item-123/img-001_thumb_400.jpg",
                    },
                    "filename": "img-001.jpg",
                }
            ]
        },
        image_urls=[
            "https://storage.googleapis.com/test-bucket/wardrobe/item-123/img-001.jpg"
        ],
    )

    result = backfill.process_item(
        item,
        dummy_service,
        storage_client=SimpleNamespace(),
        bucket_name="test-bucket",
        dry_run=False,
        retries=0,
    )

    assert result == {"updated": True, "generated": 0, "normalized": True}
    assert isinstance(item.image_urls, dict)
    assert item.image_urls["original"].endswith("img-001.jpg")
    assert "thumb_200" in item.image_urls["thumbnails"]


def test_process_item_dry_run_reports_normalization(
    dummy_service: SimpleNamespace,
) -> None:
    """Dry run should report normalization without mutating the item."""
    image_urls = [
        "https://storage.googleapis.com/test-bucket/wardrobe/item-456/img-999.jpg"
    ]
    item = SimpleNamespace(
        id="item-456",
        image_metadata={
            "images": [
                {
                    "id": "img-999",
                    "original_url": "https://storage.googleapis.com/test-bucket/wardrobe/item-456/img-999.jpg",
                    "thumbnails": {},
                }
            ]
        },
        image_urls=image_urls.copy(),
    )

    result = backfill.process_item(
        item,
        dummy_service,
        storage_client=SimpleNamespace(),
        bucket_name="test-bucket",
        dry_run=True,
        retries=0,
    )

    assert result["normalized"] is True
    # Original data remains untouched in dry run
    assert item.image_urls == image_urls
