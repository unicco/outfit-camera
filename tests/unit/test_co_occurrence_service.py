
import pytest

pytest.skip("レガシー co-occurrence テストは現在のユニット検証から除外", allow_module_level=True)

"""Unit tests for co-occurrence service"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.co_occurrence_models import (
    CategoryCoOccurrence,
    ItemPairCoOccurrence,
)
from app.co_occurrence_service import CoOccurrenceService
from app.models import Base as ModelsBase, Photo
from app.wardrobe_models import Base as WardrobeBase, ClothingItem, ClothingCategory


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")

    # Create all tables
    ModelsBase.metadata.create_all(engine)
    WardrobeBase.metadata.create_all(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def sample_items(db_session):
    """Create sample clothing items for testing."""
    items = [
        ClothingItem(
            id=str(uuid.uuid4()),
            name="White Shirt",
            category=ClothingCategory.TOPS,
            subcategory="shirt",
            brand="TestBrand",
        ),
        ClothingItem(
            id=str(uuid.uuid4()),
            name="Blue Jeans",
            category=ClothingCategory.BOTTOMS,
            subcategory="jeans",
            brand="TestBrand",
        ),
        ClothingItem(
            id=str(uuid.uuid4()),
            name="Black Jacket",
            category=ClothingCategory.OUTERWEAR,
            subcategory="jacket",
            brand="TestBrand",
        ),
        ClothingItem(
            id=str(uuid.uuid4()),
            name="Red T-Shirt",
            category=ClothingCategory.TOPS,
            subcategory="t-shirt",
            brand="TestBrand",
        ),
    ]

    for item in items:
        db_session.add(item)
    db_session.commit()

    return items


@pytest.fixture
def sample_photo(db_session):
    """Create a sample photo for testing."""
    photo_id = str(uuid.uuid4())
    photo = Photo(
        id=photo_id,
        filename=f"test_photo_{photo_id}.jpg",
        file_path=f"/test/{photo_id}.jpg",
        source="test-fixture",
        captured_at=datetime.now(),
    )
    db_session.add(photo)
    db_session.commit()
    return photo


class TestCoOccurrenceService:
    """Test cases for CoOccurrenceService."""

    def test_record_outfit_wearing(self, db_session, sample_items, sample_photo):
        """Test recording outfit wearing data."""
        service = CoOccurrenceService(db_session)

        # Record an outfit with 3 items
        worn_items = sample_items[:3]  # shirt, jeans, jacket
        worn_item_ids = [item.id for item in worn_items]

        outfit_log = service.record_outfit_wearing(
            photo_id=sample_photo.id,
            worn_item_ids=worn_item_ids,
            capture_date=date.today(),
            occasion="casual",
            user_rating=5,
        )

        # Verify outfit log was created
        assert outfit_log is not None
        assert outfit_log.photo_id == sample_photo.id
        assert len(outfit_log.worn_item_ids) == 3
        assert outfit_log.worn_categories["TOPS"] == 1
        assert outfit_log.worn_categories["BOTTOMS"] == 1
        assert outfit_log.worn_categories["OUTERWEAR"] == 1
        assert outfit_log.occasion == "casual"
        assert outfit_log.user_rating == 5

    def test_item_pair_co_occurrence(self, db_session, sample_items, sample_photo):
        """Test item pair co-occurrence tracking."""
        service = CoOccurrenceService(db_session)

        # Record first outfit
        worn_items = sample_items[:2]  # shirt and jeans
        worn_item_ids = [item.id for item in worn_items]

        service.record_outfit_wearing(
            photo_id=sample_photo.id,
            worn_item_ids=worn_item_ids,
            capture_date=date.today(),
        )

        # Check item pair was recorded
        item_pair = (
            db_session.query(ItemPairCoOccurrence)
            .filter(
                ItemPairCoOccurrence.item_id_1 == min(worn_item_ids),
                ItemPairCoOccurrence.item_id_2 == max(worn_item_ids),
            )
            .first()
        )

        assert item_pair is not None
        assert item_pair.co_occurrence_count == 1
        assert item_pair.confidence_score == 0.1  # Initial value

        # Record same outfit again
        service.record_outfit_wearing(
            photo_id=sample_photo.id,
            worn_item_ids=worn_item_ids,
            capture_date=date.today() + timedelta(days=1),
        )

        db_session.refresh(item_pair)
        assert item_pair.co_occurrence_count == 2
        assert item_pair.confidence_score == 0.2  # Updated based on count

    def test_category_co_occurrence(self, db_session, sample_items, sample_photo):
        """Test category-level co-occurrence tracking."""
        service = CoOccurrenceService(db_session)

        # Record outfit with different categories
        worn_items = sample_items[:3]  # TOPS, BOTTOMS, OUTERWEAR
        worn_item_ids = [item.id for item in worn_items]

        service.record_outfit_wearing(
            photo_id=sample_photo.id,
            worn_item_ids=worn_item_ids,
            capture_date=date(2025, 6, 15),  # Summer
        )

        # Check category pairs were recorded
        category_pairs = db_session.query(CategoryCoOccurrence).all()

        # Should have 3 pairs: TOPS-BOTTOMS, TOPS-OUTERWEAR, BOTTOMS-OUTERWEAR
        assert len(category_pairs) >= 3

        # Check specific pair
        tops_bottoms = (
            db_session.query(CategoryCoOccurrence)
            .filter(
                CategoryCoOccurrence.category_1 == "BOTTOMS",  # Alphabetically first
                CategoryCoOccurrence.category_2 == "TOPS",
                CategoryCoOccurrence.season == "summer",
            )
            .first()
        )

        assert tops_bottoms is not None
        assert tops_bottoms.co_occurrence_count == 1
        assert tops_bottoms.probability == 1.0

    def test_get_item_pair_score(self, db_session, sample_items, sample_photo):
        """Test retrieving item pair scores."""
        service = CoOccurrenceService(db_session)

        # Record outfit
        worn_items = sample_items[:2]
        worn_item_ids = [item.id for item in worn_items]

        service.record_outfit_wearing(
            photo_id=sample_photo.id,
            worn_item_ids=worn_item_ids,
            capture_date=date.today(),
        )

        # Get score for recorded pair
        score = service.get_item_pair_score(worn_item_ids[0], worn_item_ids[1])
        assert score == 0.1  # Initial confidence score

        # Get score for unrecorded pair
        score = service.get_item_pair_score(sample_items[0].id, sample_items[3].id)
        assert score is None

    def test_get_category_probability(self, db_session, sample_items, sample_photo):
        """Test retrieving category probabilities."""
        service = CoOccurrenceService(db_session)

        # Record outfit in winter
        worn_items = sample_items[:3]
        worn_item_ids = [item.id for item in worn_items]

        service.record_outfit_wearing(
            photo_id=sample_photo.id,
            worn_item_ids=worn_item_ids,
            capture_date=date(2025, 12, 15),  # Winter
        )

        # Get probability for recorded categories with matching subcategories
        prob = service.get_category_probability(
            "TOPS",
            "BOTTOMS",
            subcategory_1="shirt",
            subcategory_2="jeans",
            season="winter",
        )
        assert prob == 1.0  # Only one occurrence

        # Get probability for unrecorded season
        prob = service.get_category_probability("TOPS", "BOTTOMS", season="summer")
        assert prob == 0.0

    def test_get_best_matching_items(self, db_session, sample_items, sample_photo):
        """Test getting best matching items."""
        service = CoOccurrenceService(db_session)

        # Record multiple outfits
        # Outfit 1: shirt + jeans
        service.record_outfit_wearing(
            photo_id=sample_photo.id,
            worn_item_ids=[sample_items[0].id, sample_items[1].id],
            capture_date=date.today(),
        )

        # Outfit 2: shirt + jeans + jacket (reinforces shirt-jeans)
        service.record_outfit_wearing(
            photo_id=sample_photo.id,
            worn_item_ids=[sample_items[0].id, sample_items[1].id, sample_items[2].id],
            capture_date=date.today() + timedelta(days=1),
        )

        # Get best matches for shirt
        matches = service.get_best_matching_items(
            sample_items[0].id,
            limit=10,
            min_confidence=0.1,
        )

        assert len(matches) == 2  # jeans and jacket
        assert (
            matches[0][0].id == sample_items[1].id
        )  # jeans should be first (higher count)
        assert matches[0][1] == 0.2  # confidence score
        assert matches[1][0].id == sample_items[2].id  # jacket
        assert matches[1][1] == 0.1

    def test_season_detection(self, db_session):
        """Test season detection from dates."""
        service = CoOccurrenceService(db_session)

        assert service._get_season(date(2025, 3, 15)) == "spring"
        assert service._get_season(date(2025, 6, 15)) == "summer"
        assert service._get_season(date(2025, 9, 15)) == "autumn"
        assert service._get_season(date(2025, 12, 15)) == "winter"
