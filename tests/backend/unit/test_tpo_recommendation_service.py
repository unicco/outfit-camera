"""Unit tests for TPO recommendation engine."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from app.settings import Settings
from app.services.tpo_recommendation import TPORecommendationService, _is_patterned
from app.wardrobe_models import ClothingCategory, ClothingItem, ClothingStatus


def _create_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _add_sample_items(session: Session) -> None:
    items = [
        ClothingItem(
            name="ネイビージャケット",
            category=ClothingCategory.OUTERWEAR,
            status=ClothingStatus.ACTIVE,
            colors_palette={"palette": [{"hex": "#1c2a4a", "position": 1}]},
            pattern="solid",
            material="wool",
            occasion=["business"],
        ),
        ClothingItem(
            name="ホワイトシャツ",
            category=ClothingCategory.TOPS,
            status=ClothingStatus.ACTIVE,
            colors_palette={"palette": [{"hex": "#f7f7f7", "position": 1}]},
            pattern="solid",
            material="cotton",
            occasion=["business"],
        ),
        ClothingItem(
            name="グレースラックス",
            category=ClothingCategory.BOTTOMS,
            status=ClothingStatus.ACTIVE,
            colors_palette={"palette": [{"hex": "#6b6b6b", "position": 1}]},
            pattern="solid",
            material="wool",
            occasion=["business"],
        ),
        ClothingItem(
            name="ブラウンレザーシューズ",
            category=ClothingCategory.SHOES,
            status=ClothingStatus.ACTIVE,
            colors_palette={"palette": [{"hex": "#5c3a21", "position": 1}]},
            material="leather",
            occasion=["business"],
        ),
        ClothingItem(
            name="ブラックバッグ",
            category=ClothingCategory.BAG,
            status=ClothingStatus.ACTIVE,
            colors_palette={"palette": [{"hex": "#000000", "position": 1}]},
            pattern="solid",
            material="leather",
            occasion=["business"],
        ),
    ]
    session.add_all(items)
    session.commit()


def test_recommendations_include_formality_in_response() -> None:
    session = _create_session()
    try:
        _add_sample_items(session)
        service = TPORecommendationService(session, Settings())

        context = service.build_context(
            weather="rainy",
            temperature=12.0,
            occasion="business",
            user_schedule=["会議"],
        )

        outfits = service.recommend_outfits(context, weather_snapshot=None, limit=3)

        assert outfits, "At least one outfit should be suggested"
        top_outfit = outfits[0]
        assert len(top_outfit.items) >= 2, "Outfit should contain multiple items"

        for entry in top_outfit.items:
            assert entry.formality.get("formal", 0) > 0.3
    finally:
        session.close()


def test_layer_requirement_suppresses_outer_when_not_necessary() -> None:
    session = _create_session()
    try:
        _add_sample_items(session)
        service = TPORecommendationService(session, Settings())
        context = service.build_context(
            weather="cloudy",
            temperature=22.0,
            occasion=None,
            user_schedule=[],
        )

        outfits = service.recommend_outfits(context, weather_snapshot=None, limit=3)
        assert outfits, "Outfits should be recommended"
        for outfit in outfits:
            assert all(
                entry.item.category != ClothingCategory.OUTERWEAR for entry in outfit.items
            ), "Outerwear should be omitted for long-sleeve requirement"
    finally:
        session.close()


def test_outfit_includes_shoes_and_bag() -> None:
    session = _create_session()
    try:
        _add_sample_items(session)
        service = TPORecommendationService(session, Settings())
        context = service.build_context(
            weather="cloudy",
            temperature=18.0,
            occasion="business",
            user_schedule=["会議"],
        )

        outfits = service.recommend_outfits(context, weather_snapshot=None, limit=3)
        assert outfits, "Outfits should be recommended"
        top_outfit = outfits[0]
        categories = {entry.item.category for entry in top_outfit.items}
        assert ClothingCategory.SHOES in categories, "Shoes should be included in outfit"
        assert ClothingCategory.BAG in categories, "Bag should be included in outfit"
    finally:
        session.close()


def test_patterned_top_and_bottom_not_combined() -> None:
    session = _create_session()
    try:
        _add_sample_items(session)
        top_item = (
            session.query(ClothingItem)
            .filter(ClothingItem.category == ClothingCategory.TOPS)
            .first()
        )
        assert top_item is not None
        top_item.pattern = "striped"

        patterned_bottom = (
            session.query(ClothingItem)
            .filter(ClothingItem.category == ClothingCategory.BOTTOMS)
            .first()
        )
        assert patterned_bottom is not None
        patterned_bottom.pattern = "plaid"

        solid_bottom = ClothingItem(
            name="ネイビースラックス",
            category=ClothingCategory.BOTTOMS,
            status=ClothingStatus.ACTIVE,
            pattern="solid",
            material="wool",
            occasion=["business"],
        )
        session.add(solid_bottom)
        session.commit()

        service = TPORecommendationService(session, Settings())
        context = service.build_context(
            weather="cloudy",
            temperature=18.0,
            occasion="business",
            user_schedule=["会議"],
        )

        outfits = service.recommend_outfits(context, weather_snapshot=None, limit=5)
        assert outfits, "Outfits should be recommended"
        for outfit in outfits:
            top_patterns = [
                entry.item.pattern for entry in outfit.items if entry.item.category == ClothingCategory.TOPS
            ]
            bottom_patterns = [
                entry.item.pattern for entry in outfit.items if entry.item.category == ClothingCategory.BOTTOMS
            ]
            if top_patterns and bottom_patterns:
                assert not (
                    _is_patterned(top_patterns[0]) and _is_patterned(bottom_patterns[0])
                ), "Patterned top and bottom should not be paired"
    finally:
        session.close()
