import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.routers.outfits import OutfitRecordCreate, create_outfit_record
from app.models import OutfitItem, OutfitRecord
from app.wardrobe_models import ClothingItem, ClothingCategory, ClothingStatus


@pytest.mark.asyncio
async def test_create_outfit_record_allows_manual_entry_without_photo():
    """Manual outfit records should persist even when no photo is available."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.refresh = MagicMock()

    clothing_item_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_clothing_item = ClothingItem(
        id=clothing_item_id,
        name="Manual Item",
        category=ClothingCategory.TOPS,
        status=ClothingStatus.ACTIVE,
    )
    mock_clothing_item.usage_count = 0
    mock_clothing_item.last_used_date = None

    outfit_query = MagicMock()
    outfit_filter_chain = MagicMock()
    outfit_filter_chain.filter.return_value = outfit_filter_chain
    outfit_filter_chain.first.return_value = None
    outfit_query.filter.return_value = outfit_filter_chain

    clothing_query = MagicMock()
    clothing_filter = MagicMock()
    clothing_filter.first.return_value = mock_clothing_item
    clothing_query.filter.return_value = clothing_filter

    def query_side_effect(model_class):
        if model_class == OutfitRecord:
            return outfit_query
        if model_class == OutfitItem:
            empty_filter = MagicMock()
            empty_filter.all.return_value = []
            query = MagicMock()
            query.filter.return_value = empty_filter
            return query
        if model_class == ClothingItem:
            return clothing_query
        return MagicMock()

    db.query.side_effect = query_side_effect

    record_data = OutfitRecordCreate(
        photo_id="",
        clothing_item_ids=[clothing_item_id],
        notes="Manual selection without photo",
        recorded_at=datetime(2025, 10, 5, 12, 0, 0).isoformat(),
    )

    with patch("app.routers.outfits.CoOccurrenceService") as mock_service_cls:
        mock_service = MagicMock()
        mock_service.record_outfit_wearing = MagicMock()
        mock_service_cls.return_value = mock_service

        result = await create_outfit_record(record_data, db)

    # Verify the first add() call persisted the OutfitRecord without a photo reference
    assert db.add.call_count >= 1
    created_record = db.add.call_args_list[0][0][0]
    assert created_record.photo_id is None

    assert result["photo_id"] is None
    assert result["status"] == "success"

    # Ensure wardrobe usage stats were updated
    assert mock_clothing_item.usage_count == 1
    assert mock_clothing_item.last_used_date is not None

    # Co-occurrence service should receive None photo_id
    mock_service.record_outfit_wearing.assert_called_once()
    kwargs = mock_service.record_outfit_wearing.call_args.kwargs
    assert kwargs["photo_id"] is None
    assert kwargs["worn_item_ids"] == [clothing_item_id]

    db.commit.assert_called_once()
