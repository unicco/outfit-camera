import pytest
from datetime import datetime
from unittest.mock import MagicMock

from app.routers.outfits import OutfitRecordCreate, create_outfit_record
from app.models import OutfitItem, OutfitRecord, OutfitExternalRentalItem
from app.wardrobe_models import ClothingItem, ClothingCategory, ClothingStatus
from app.external_rental_models import ExternalRentalItem, ExternalRentalSource


@pytest.mark.asyncio
async def test_create_outfit_record_links_external_rentals():
    """ExternalRentalItemIds を指定した場合にリンクテーブルが作成され、着用回数が更新される。."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.refresh = MagicMock()

    clothing_item_id = "550e8400-e29b-41d4-a716-446655440000"
    rental_item_id = "9c8a0c24-02b4-4a8e-a2c2-6ff25de2cadf"

    clothing_item = ClothingItem(
        id=clothing_item_id,
        name="Test Tops",
        category=ClothingCategory.TOPS,
        status=ClothingStatus.ACTIVE,
    )
    clothing_item.usage_count = 0
    clothing_item.last_used_date = None

    rental_item = ExternalRentalItem(
        id=rental_item_id,
        source=ExternalRentalSource.EXAMPLE_RENTAL,
        source_item_id="aa-001",
        name="Rental Dress",
    )
    rental_item.wear_count = 2
    rental_item.last_worn_at = None

    outfit_query = MagicMock()
    outfit_query.filter.return_value = MagicMock(first=MagicMock(return_value=None))

    outfit_item_query = MagicMock()
    outfit_item_filter = MagicMock()
    outfit_item_filter.all.return_value = []
    outfit_item_query.filter.return_value = outfit_item_filter

    clothing_query = MagicMock()
    clothing_filter = MagicMock()
    clothing_filter.first.return_value = clothing_item
    clothing_query.filter.return_value = clothing_filter

    rental_query = MagicMock()
    rental_filter = MagicMock()
    rental_filter.all.return_value = [rental_item]
    rental_query.filter.return_value = rental_filter

    def query_side_effect(model_class):
        if model_class == OutfitRecord:
            return outfit_query
        if model_class == OutfitItem:
            return outfit_item_query
        if model_class == ClothingItem:
            return clothing_query
        if model_class == ExternalRentalItem:
            return rental_query
        return MagicMock()

    db.query.side_effect = query_side_effect

    record_data = OutfitRecordCreate(
        photo_id="",
        clothing_item_ids=[clothing_item_id],
        external_rental_item_ids=[rental_item_id],
        notes="Rental linked outfit",
        recorded_at=datetime(2025, 2, 6, 12, 0, 0).isoformat(),
    )

    await create_outfit_record(record_data, db)

    # 外部レンタルとのリンクが追加される
    external_link_call = next(
        (
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], OutfitExternalRentalItem)
        ),
        None,
    )
    assert external_link_call is not None
    assert external_link_call.external_rental_item_id == rental_item_id

    # 着用回数がインクリメントされ、最終着用日が設定される
    assert rental_item.wear_count == 3
    assert rental_item.last_worn_at is not None
