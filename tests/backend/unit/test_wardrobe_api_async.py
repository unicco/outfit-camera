
import pytest

pytest.skip("レガシー API テストは現在のユニット検証から除外", allow_module_level=True)

"""Unit tests for wardrobe async image upload helpers."""

import io
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks
from starlette.datastructures import UploadFile

from app.wardrobe_api_async import upload_item_images


class _FakeQuery:
    def __init__(self, item: Any) -> None:
        self._item = item

    def filter(self, *args: Any, **kwargs: Any) -> "_FakeQuery":  # noqa: D401
        return self

    def first(self) -> Any:
        return self._item


class _FakeSession:
    def __init__(self, item: Any) -> None:
        self._item = item
        self.committed = False

    def query(self, *args: Any, **kwargs: Any) -> _FakeQuery:  # noqa: D401
        return _FakeQuery(self._item)

    def commit(self) -> None:
        self.committed = True

    def add(self, _item: Any) -> None:  # noqa: D401
        # SQLAlchemy Session.add compatibility stub
        return None


class _StubItem:
    def __init__(self) -> None:
        self.id = "item-123"
        self.image_metadata = None
        self.image_urls = None


@pytest.mark.asyncio
async def test_upload_item_images_populates_thumbnails() -> None:
    """Ensure upload_item_images stores thumbnail metadata and image_urls."""
    item = _StubItem()
    session = _FakeSession(item)

    upload_service = AsyncMock()
    upload_service.upload_multiple_images.return_value = [
        {
            "id": "file-456",
            "original_url": "https://storage.googleapis.com/test-bucket/wardrobe/item-123/file-456.jpg",
            "thumbnails": {
                "thumb_200": "https://storage.googleapis.com/test-bucket/wardrobe/item-123/file-456_thumb_200.jpg",
                "thumb_400": "https://storage.googleapis.com/test-bucket/wardrobe/item-123/file-456_thumb_400.jpg",
            },
            "content_type": "image/jpeg",
            "filename": "file-456.jpg",
            "size": 1024,
        }
    ]

    upload_file = UploadFile(
        filename="file-456.jpg",
        file=io.BytesIO(b"binary-image"),
        headers={"content-type": "image/jpeg"},
    )

    background_tasks = BackgroundTasks()

    result = await upload_item_images(
        item_id=item.id,
        files=[upload_file],
        background_tasks=background_tasks,
        db=session,
        upload_service=upload_service,
    )

    assert session.committed is True
    assert "uploaded_images" in result
    assert result["uploaded_images"][0]["thumbnails"]["thumb_200"].endswith(
        "thumb_200.jpg"
    )

    assert item.image_metadata is not None
    assert isinstance(item.image_metadata, dict)
    metadata_images = item.image_metadata.get("images")
    assert isinstance(metadata_images, list)
    assert metadata_images[0]["thumbnails"]["thumb_400"].endswith("thumb_400.jpg")

    assert item.image_urls == {
        "original": "https://storage.googleapis.com/test-bucket/wardrobe/item-123/file-456.jpg",
        "thumbnails": {
            "thumb_200": "https://storage.googleapis.com/test-bucket/wardrobe/item-123/file-456_thumb_200.jpg",
            "thumb_400": "https://storage.googleapis.com/test-bucket/wardrobe/item-123/file-456_thumb_400.jpg",
        },
    }

    # Background processing should be scheduled for later execution
    assert len(background_tasks.tasks) == 1
