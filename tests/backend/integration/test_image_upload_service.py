"""Tests for Google Cloud Storage image upload service."""

import io
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.image_upload_service import ImageUploadService, get_image_upload_service

# ImageUploadService is GCS-only (Issue #437 removed local storage) and the
# backend test conftest forces STORAGE_TYPE=filesystem, so constructing the
# service raises without a real GCS setup. Several tests here also instantiate a
# live storage.Client(). Skip the whole module unless GCS credentials are
# present; run with GOOGLE_APPLICATION_CREDENTIALS + STORAGE_TYPE=gcs to exercise
# them locally (integration test triage).
_GCS_CREDS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
pytestmark = pytest.mark.skipif(
    not (_GCS_CREDS and os.path.exists(_GCS_CREDS)),
    reason="GCS credentials not configured (GOOGLE_APPLICATION_CREDENTIALS)",
)


@pytest.fixture
def mock_gcs_client():
    """Mock GCS client and bucket."""
    with patch("app.image_upload_service.storage.Client") as mock_client:
        # Mock client
        client = MagicMock()
        mock_client.return_value = client

        # Mock bucket
        bucket = MagicMock()
        client.bucket.return_value = bucket

        # Mock blob
        blob = MagicMock()
        blob.public_url = "https://storage.googleapis.com/test-bucket/test.jpg"
        bucket.blob.return_value = blob

        yield client, bucket, blob


@pytest.fixture
def mock_upload_file():
    """Create a mock UploadFile object."""
    # Create a real image for testing
    img = Image.new("RGB", (100, 100), color="red")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="JPEG")
    img_bytes.seek(0)

    # Mock UploadFile
    file = AsyncMock()
    file.filename = "test.jpg"
    file.content_type = "image/jpeg"
    file.read = AsyncMock(return_value=img_bytes.getvalue())

    return file


@pytest.fixture
def mock_env():
    """Mock environment variables."""
    with patch.dict(os.environ, {"GCS_BUCKET_NAME": "test-bucket"}):
        yield


@pytest.mark.asyncio
async def test_upload_wardrobe_image(mock_gcs_client, mock_upload_file, mock_env):
    """Test uploading a single wardrobe image."""
    client, bucket, blob = mock_gcs_client

    # Create service and upload
    service = ImageUploadService()
    result = await service.upload_wardrobe_image(mock_upload_file, "item-123")

    # Verify result
    assert "id" in result
    assert result["original_url"] == blob.public_url
    assert "thumbnails" in result
    assert "thumb_200" in result["thumbnails"]
    assert "thumb_400" in result["thumbnails"]
    assert result["size"] > 0
    assert result["content_type"] == "image/jpeg"
    assert result["filename"] == "test.jpg"

    # Verify blob upload was called
    assert blob.upload_from_string.called
    assert blob.make_public.called


@pytest.mark.asyncio
async def test_upload_multiple_images(mock_gcs_client, mock_upload_file, mock_env):
    """Test uploading multiple images."""
    # Create multiple files
    files = [mock_upload_file, mock_upload_file, mock_upload_file]

    service = ImageUploadService()
    results = await service.upload_multiple_images(files, "item-123")

    # Verify results
    assert len(results) == 3
    for result in results:
        assert "id" in result
        assert "original_url" in result
        assert "thumbnails" in result


def test_generate_thumbnail(mock_env):
    """Test thumbnail generation."""
    # Create a test image
    img = Image.new("RGB", (800, 600), color="blue")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="JPEG")
    img_bytes.seek(0)

    service = ImageUploadService()
    thumbnail_bytes = service._generate_thumbnail(img_bytes.getvalue(), 200)

    # Verify thumbnail
    thumbnail = Image.open(io.BytesIO(thumbnail_bytes))
    assert thumbnail.size == (200, 200)  # Should be square
    assert thumbnail.mode == "RGB"


def test_generate_thumbnail_with_transparency(mock_env):
    """Test thumbnail generation with transparent images."""
    # Create a transparent image
    img = Image.new("RGBA", (400, 400), color=(255, 0, 0, 128))
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    service = ImageUploadService()
    thumbnail_bytes = service._generate_thumbnail(img_bytes.getvalue(), 100)

    # Verify thumbnail has no transparency
    thumbnail = Image.open(io.BytesIO(thumbnail_bytes))
    assert thumbnail.size == (100, 100)
    assert thumbnail.mode == "RGB"  # Transparency removed


@pytest.mark.asyncio
async def test_upload_with_invalid_extension(mock_gcs_client, mock_env):
    """Test uploading with invalid file extension."""
    # Create file with invalid extension
    file = AsyncMock()
    file.filename = "test.txt"
    file.content_type = "text/plain"
    file.read = AsyncMock(return_value=b"not an image")

    service = ImageUploadService()
    result = await service.upload_wardrobe_image(file, "item-123")

    # Should default to jpg extension
    assert result["filename"] == "test.txt"
    assert ".jpg" in mock_gcs_client[1].blob.call_args[0][0]


def test_get_image_upload_service(mock_env):
    """Test service singleton pattern."""
    # Get service twice
    service1 = get_image_upload_service()
    service2 = get_image_upload_service()

    # Should be the same instance
    assert service1 is service2


@pytest.mark.asyncio
async def test_upload_error_handling(mock_gcs_client, mock_upload_file, mock_env):
    """Test error handling during upload."""
    # Make blob upload fail
    mock_gcs_client[2].upload_from_string.side_effect = Exception("Upload failed")

    service = ImageUploadService()

    # Should raise exception
    with pytest.raises(Exception, match="Upload failed"):
        await service.upload_wardrobe_image(mock_upload_file, "item-123")


@pytest.mark.asyncio
async def test_thumbnail_generation_error(mock_gcs_client, mock_env):
    """Test handling of thumbnail generation errors."""
    # Create invalid image data
    file = AsyncMock()
    file.filename = "test.jpg"
    file.content_type = "image/jpeg"
    file.read = AsyncMock(return_value=b"invalid image data")

    service = ImageUploadService()
    result = await service.upload_wardrobe_image(file, "item-123")

    # Original should be uploaded but thumbnails may be None
    assert "original_url" in result
    assert "thumbnails" in result


@pytest.mark.asyncio
async def test_delete_wardrobe_images(mock_gcs_client, mock_env):
    """Test deleting all images for an item."""
    client, bucket, blob = mock_gcs_client

    # Mock blob list
    blob1 = MagicMock()
    blob2 = MagicMock()
    bucket.list_blobs.return_value = [blob1, blob2]

    service = ImageUploadService()
    await service.delete_wardrobe_images("item-123")

    # Verify list_blobs was called with correct prefix
    bucket.list_blobs.assert_called_with(prefix="wardrobe/item-123/")

    # Verify both blobs were deleted
    blob1.delete.assert_called_once()
    blob2.delete.assert_called_once()


def test_init_without_bucket_name():
    """Test initialization without GCS_BUCKET_NAME."""
    with patch.dict(os.environ, {}, clear=True):
        # Should use default bucket name
        service = ImageUploadService()
        assert service.bucket_name == "coordinate-recorder-wardrobe"
