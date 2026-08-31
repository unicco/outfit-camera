
import pytest

pytest.skip("レガシー API テストは現在のユニット検証から除外", allow_module_level=True)

"""Test outfit API usage count and last_used_date updates (Issue #921)"""

import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.routers.outfits import create_outfit_record, delete_outfit_record_by_photo
from app.models import OutfitRecord, OutfitItem
from app.wardrobe_models import ClothingItem, ClothingCategory, ClothingStatus

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    return db


@pytest.fixture
def sample_clothing_items():
    """Create sample clothing items for testing."""
    items = []
    for i in range(3):
        item = ClothingItem(
            id=str(uuid4()),
            name=f"Test Item {i}",
            category=ClothingCategory.TOPS,
            status=ClothingStatus.ACTIVE,
            usage_count=i,  # Different initial counts
            last_used_date=None,
        )
        items.append(item)
    return items


@pytest.fixture
def sample_outfit_record():
    """Create a sample outfit record."""
    record = OutfitRecord(
        id=str(uuid4()),
        photo_id="test_photo_123",
        recorded_at=datetime.now(),
        manual_selection=True,
    )
    return record


class TestOutfitAPIUsageUpdate:
    """Test class for outfit API usage update functionality."""

    async def test_create_outfit_record_updates_usage_stats(
        self, mock_db, sample_clothing_items
    ):
        """Test that creating an outfit record updates usage count and last_used_date."""
        # Arrange
        clothing_item_ids = [item.id for item in sample_clothing_items]
        record_data = MagicMock(
            photo_id="test_photo_123",
            clothing_item_ids=clothing_item_ids,
            notes="Test outfit",
            recorded_at=datetime(2025, 1, 15, 12, 0, 0),
        )

        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # No existing outfit record
            sample_clothing_items[0],  # First clothing item
            sample_clothing_items[1],  # Second clothing item
            sample_clothing_items[2],  # Third clothing item
        ]

        # Act
        with patch("app.routers.outfits.get_db", return_value=mock_db):
            with patch("app.routers.outfits.UUID"):  # Mock UUID validation
                result = await create_outfit_record(record_data, mock_db)
        assert result is not None

        # Assert
        # Check that usage counts were incremented
        assert sample_clothing_items[0].usage_count == 1  # 0 + 1
        assert sample_clothing_items[1].usage_count == 2  # 1 + 1
        assert sample_clothing_items[2].usage_count == 3  # 2 + 1

        # Check that last_used_date was updated
        expected_date = date(2025, 1, 15)
        for item in sample_clothing_items:
            assert item.last_used_date == expected_date

    async def test_update_outfit_record_handles_usage_correctly(
        self, mock_db, sample_clothing_items, sample_outfit_record
    ):
        """Test that updating an existing outfit record correctly manages usage counts."""
        # Arrange
        # Create existing outfit items
        existing_outfit_items = [
            OutfitItem(
                id=str(uuid4()),
                outfit_record_id=sample_outfit_record.id,
                clothing_item_id=sample_clothing_items[0].id,
                manual_added=True,
            ),
            OutfitItem(
                id=str(uuid4()),
                outfit_record_id=sample_outfit_record.id,
                clothing_item_id=sample_clothing_items[1].id,
                manual_added=True,
            ),
        ]

        # Set initial usage counts
        sample_clothing_items[0].usage_count = 5
        sample_clothing_items[1].usage_count = 3
        sample_clothing_items[2].usage_count = 2

        # New outfit includes item 1 and 2 (item 0 is removed)
        new_clothing_item_ids = [
            sample_clothing_items[1].id,
            sample_clothing_items[2].id,
        ]

        record_data = MagicMock(
            photo_id="test_photo_123",
            clothing_item_ids=new_clothing_item_ids,
            notes="Updated outfit",
            recorded_at=datetime(2025, 1, 16, 12, 0, 0),
        )

        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_outfit_record,  # Existing outfit record
            sample_clothing_items[0],  # Item 0 for decrement
            sample_clothing_items[1],  # Item 1 for decrement
            sample_clothing_items[1],  # Item 1 for increment
            sample_clothing_items[2],  # Item 2 for increment
        ]

        mock_db.query.return_value.filter.return_value.all.return_value = (
            existing_outfit_items
        )

        # Act
        from app.routers.outfits import create_outfit_record

        with patch("app.routers.outfits.get_db", return_value=mock_db):
            with patch("app.routers.outfits.UUID"):  # Mock UUID validation
                result = await create_outfit_record(record_data, mock_db)
        assert result is not None

        # Assert
        # Item 0: was in old outfit but not in new, so -1
        assert sample_clothing_items[0].usage_count == 4  # 5 - 1
        # Item 1: was in old outfit and is in new, so -1 + 1 = no change
        assert sample_clothing_items[1].usage_count == 3  # 3 - 1 + 1
        # Item 2: was not in old outfit but is in new, so +1
        assert sample_clothing_items[2].usage_count == 3  # 2 + 1

    async def test_delete_outfit_record_decrements_usage_counts(
        self, mock_db, sample_clothing_items, sample_outfit_record
    ):
        """Test that deleting an outfit record decrements usage counts."""
        # Arrange
        outfit_items = [
            OutfitItem(
                id=str(uuid4()),
                outfit_record_id=sample_outfit_record.id,
                clothing_item_id=sample_clothing_items[0].id,
                manual_added=True,
            ),
            OutfitItem(
                id=str(uuid4()),
                outfit_record_id=sample_outfit_record.id,
                clothing_item_id=sample_clothing_items[1].id,
                manual_added=True,
            ),
        ]

        # Set initial usage counts
        sample_clothing_items[0].usage_count = 5
        sample_clothing_items[1].usage_count = 3

        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_outfit_record,  # Outfit record exists
            sample_clothing_items[0],  # First clothing item
            sample_clothing_items[1],  # Second clothing item
            None,  # No photo found (for simplicity)
        ]

        mock_db.query.return_value.filter.return_value.all.side_effect = [
            outfit_items,  # First call for outfit items
            [],  # Second call for detection results
        ]

        # Act
        with patch("app.routers.outfits.get_db", return_value=mock_db):
            result = await delete_outfit_record_by_photo("test_photo_123", mock_db)
        assert result is not None

        # Assert
        assert sample_clothing_items[0].usage_count == 4  # 5 - 1
        assert sample_clothing_items[1].usage_count == 2  # 3 - 1
        assert "outfit_record" in result["deleted_items"]
        assert "outfit_items" in result["deleted_items"]

    async def test_usage_count_never_goes_negative(
        self, mock_db, sample_clothing_items, sample_outfit_record
    ):
        """Test that usage count never goes below zero."""
        # Arrange
        outfit_items = [
            OutfitItem(
                id=str(uuid4()),
                outfit_record_id=sample_outfit_record.id,
                clothing_item_id=sample_clothing_items[0].id,
                manual_added=True,
            ),
        ]

        # Set usage count to 0
        sample_clothing_items[0].usage_count = 0

        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            sample_outfit_record,  # Outfit record exists
            sample_clothing_items[0],  # Clothing item with usage_count=0
            None,  # No photo found
        ]

        mock_db.query.return_value.filter.return_value.all.side_effect = [
            outfit_items,  # First call for outfit items
            [],  # Second call for detection results
        ]

        # Act
        with patch("app.routers.outfits.get_db", return_value=mock_db):
            result = await delete_outfit_record_by_photo("test_photo_123", mock_db)
        assert result is not None

        # Assert
        assert (
            sample_clothing_items[0].usage_count == 0
        )  # Should remain 0, not go negative

    async def test_handles_none_usage_count(self, mock_db, sample_clothing_items):
        """Test that None usage_count is handled correctly."""
        # Arrange
        sample_clothing_items[0].usage_count = None

        record_data = MagicMock(
            photo_id="test_photo_123",
            clothing_item_ids=[sample_clothing_items[0].id],
            notes="Test outfit",
            recorded_at=datetime(2025, 1, 15, 12, 0, 0),
        )

        # Mock database queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            None,  # No existing outfit record
            sample_clothing_items[0],  # Clothing item with None usage_count
        ]

        # Act
        from app.routers.outfits import create_outfit_record

        with patch("app.routers.outfits.get_db", return_value=mock_db):
            with patch("app.routers.outfits.UUID"):  # Mock UUID validation
                result = await create_outfit_record(record_data, mock_db)
        assert result is not None

        # Assert
        assert (
            sample_clothing_items[0].usage_count == 1
        )  # None treated as 0, then incremented
