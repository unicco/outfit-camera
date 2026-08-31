"""Unit tests for disposal date handling in wardrobe API."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from datetime import date

from app.routers.wardrobe import (
    ClothingItemCreate,
    SaleInfoUpdate,
    create_clothing_item,
    get_wardrobe_items,
    update_sale_info,
)
from app.wardrobe_models import ClothingStatus


@pytest.mark.asyncio
async def test_get_wardrobe_items_invalid_recorded_date() -> None:
    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_wardrobe_items(recorded_date="2024-13-01", db=db)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid recorded_date format. Use YYYY-MM-DD"


@pytest.mark.asyncio
async def test_create_clothing_item_invalid_disposal_date() -> None:
    db = MagicMock()
    payload = ClothingItemCreate(
        name="Test Item",
        category="tops",
        disposal_date="not-a-date",
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_clothing_item(payload, db=db)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid disposal date format. Use YYYY-MM-DD"


@pytest.mark.asyncio
async def test_update_sale_info_sets_disposal_date_without_changing_status() -> None:
    """処分情報を入れても status は自動変更しない（ステータスは明示指定のみ）."""

    class DummyItem:
        sale_platform = None
        sale_price = 0
        sale_commission = 0
        disposal_date = None
        status = ClothingStatus.ACTIVE

    item = DummyItem()

    filter_mock = MagicMock()
    filter_mock.first.return_value = item

    db = MagicMock()
    db.query.return_value.filter.return_value = filter_mock

    sale_info = SaleInfoUpdate(
        sale_price=5000,
        disposal_date="2024-12-05",
    )

    await update_sale_info("test-item", sale_info, db=db)

    assert item.disposal_date == date(2024, 12, 5)
    # 処分情報を入れても status は自動で DISPOSED にならない
    assert item.status == ClothingStatus.ACTIVE
    db.commit.assert_called_once()
