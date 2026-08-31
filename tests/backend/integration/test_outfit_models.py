"""Unit tests for Outfit models
Issue #200 implementation tests.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, OutfitItem, OutfitRecord
from app.wardrobe_models import ClothingCategory, ClothingItem, ClothingStatus


# Test database setup
@pytest.fixture
def db_session():
    """Create a test database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()


@pytest.fixture
def sample_clothing_item(db_session):
    """Create a sample clothing item for testing."""
    clothing_item = ClothingItem(
        name="Test Shirt",
        category=ClothingCategory.TOPS,
        colors_palette={"palette": [{"hex": "#FFFFFF", "position": 1}]},
        subcategory="t-shirt",
        brand="Test Brand",
        status=ClothingStatus.ACTIVE,
    )
    db_session.add(clothing_item)
    db_session.commit()
    db_session.refresh(clothing_item)
    return clothing_item


class TestOutfitRecord:
    """Test OutfitRecord model."""

    def test_create_outfit_record(self, db_session):
        """Test creating an outfit record."""
        photo_id = f"test-photo-{uuid.uuid4()}"

        outfit_record = OutfitRecord(
            photo_id=photo_id, manual_selection=True, notes="Test outfit record"
        )

        db_session.add(outfit_record)
        db_session.commit()
        db_session.refresh(outfit_record)

        assert outfit_record.id is not None
        assert outfit_record.photo_id == photo_id
        assert outfit_record.manual_selection is True
        assert outfit_record.notes == "Test outfit record"
        assert outfit_record.recorded_at is not None
        assert outfit_record.created_at is not None
        assert outfit_record.updated_at is not None

    def test_outfit_record_defaults(self, db_session):
        """Test outfit record default values."""
        outfit_record = OutfitRecord(photo_id="test-photo")

        db_session.add(outfit_record)
        db_session.commit()
        db_session.refresh(outfit_record)

        assert outfit_record.manual_selection is True  # Default value
        assert outfit_record.confidence_score is None
        assert outfit_record.notes is None


class TestOutfitItem:
    """Test OutfitItem model."""

    def test_create_outfit_item(self, db_session, sample_clothing_item):
        """Test creating an outfit item."""
        # Create outfit record first
        outfit_record = OutfitRecord(photo_id="test-photo")
        db_session.add(outfit_record)
        db_session.commit()
        db_session.refresh(outfit_record)

        # Create outfit item
        outfit_item = OutfitItem(
            outfit_record_id=outfit_record.id,
            clothing_item_id=sample_clothing_item.id,
            manual_added=True,
            position_x=100,
            position_y=200,
        )

        db_session.add(outfit_item)
        db_session.commit()
        db_session.refresh(outfit_item)

        assert outfit_item.id is not None
        assert outfit_item.outfit_record_id == outfit_record.id
        assert outfit_item.clothing_item_id == sample_clothing_item.id
        assert outfit_item.manual_added is True
        assert outfit_item.position_x == 100
        assert outfit_item.position_y == 200
        assert outfit_item.created_at is not None

    def test_outfit_item_defaults(self, db_session, sample_clothing_item):
        """Test outfit item default values."""
        outfit_record = OutfitRecord(photo_id="test-photo")
        db_session.add(outfit_record)
        db_session.commit()
        db_session.refresh(outfit_record)

        outfit_item = OutfitItem(
            outfit_record_id=outfit_record.id, clothing_item_id=sample_clothing_item.id
        )

        db_session.add(outfit_item)
        db_session.commit()
        db_session.refresh(outfit_item)

        assert outfit_item.manual_added is True  # Default value
        assert outfit_item.detection_confidence is None
        assert outfit_item.position_x is None
        assert outfit_item.position_y is None

    def test_unique_constraint(self, db_session, sample_clothing_item):
        """Test unique constraint on outfit_record_id and clothing_item_id."""
        outfit_record = OutfitRecord(photo_id="test-photo")
        db_session.add(outfit_record)
        db_session.commit()
        db_session.refresh(outfit_record)

        # First outfit item
        outfit_item1 = OutfitItem(
            outfit_record_id=outfit_record.id, clothing_item_id=sample_clothing_item.id
        )
        db_session.add(outfit_item1)
        db_session.commit()

        # Try to add duplicate - should fail
        outfit_item2 = OutfitItem(
            outfit_record_id=outfit_record.id, clothing_item_id=sample_clothing_item.id
        )
        db_session.add(outfit_item2)

        with pytest.raises(Exception):  # IntegrityError in real PostgreSQL
            db_session.commit()


class TestOutfitRelationships:
    """Test relationships between models."""

    def test_outfit_record_outfit_items_relationship(
        self, db_session, sample_clothing_item
    ):
        """Test the relationship from OutfitRecord to OutfitItems."""
        outfit_record = OutfitRecord(photo_id="test-photo")
        db_session.add(outfit_record)
        db_session.commit()
        db_session.refresh(outfit_record)

        # Add multiple outfit items
        for i in range(3):
            # Create additional clothing items
            clothing_item = ClothingItem(
                name=f"Test Item {i}",
                category=ClothingCategory.TOPS,
                color_primary="blue",
                status=ClothingStatus.ACTIVE,
            )
            db_session.add(clothing_item)
            db_session.commit()
            db_session.refresh(clothing_item)

            outfit_item = OutfitItem(
                outfit_record_id=outfit_record.id, clothing_item_id=clothing_item.id
            )
            db_session.add(outfit_item)

        db_session.commit()

        # Test relationship
        db_session.refresh(outfit_record)
        assert len(outfit_record.outfit_items) == 3

        for outfit_item in outfit_record.outfit_items:
            assert outfit_item.outfit_record_id == outfit_record.id

    def test_cascade_delete(self, db_session, sample_clothing_item):
        """Test cascade delete functionality."""
        outfit_record = OutfitRecord(photo_id="test-photo")
        db_session.add(outfit_record)
        db_session.commit()
        db_session.refresh(outfit_record)

        outfit_item = OutfitItem(
            outfit_record_id=outfit_record.id, clothing_item_id=sample_clothing_item.id
        )
        db_session.add(outfit_item)
        db_session.commit()

        outfit_item_id = outfit_item.id

        # Delete outfit record - should cascade delete outfit items
        db_session.delete(outfit_record)
        db_session.commit()

        # Verify outfit item was deleted
        deleted_item = (
            db_session.query(OutfitItem).filter(OutfitItem.id == outfit_item_id).first()
        )
        assert deleted_item is None
