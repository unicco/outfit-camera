"""Tests for image_utils.py."""

import io
import numpy as np
import pytest
from PIL import Image

from app.utils.image_utils import (
    convert_cv2_to_pil,
    convert_pil_to_cv2,
    ensure_rgb_format,
    get_image_dimensions,
    load_image_from_bytes,
    resize_image_to_square,
    resize_image_with_aspect_ratio,
    save_image_to_bytes,
)


class TestImageUtils:
    """Test image processing utilities."""

    @pytest.fixture
    def sample_image_bytes(self):
        """Create sample image bytes for testing."""
        # Create a simple RGB image
        img = Image.new("RGB", (100, 150), color=(255, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        return buffer.getvalue()

    @pytest.fixture
    def sample_rgba_image_bytes(self):
        """Create sample RGBA image bytes for testing."""
        # Create RGBA image with transparency
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_load_image_from_bytes_cv2(self, sample_image_bytes):
        """Test loading image as OpenCV format."""
        img = load_image_from_bytes(sample_image_bytes, mode="cv2")
        assert img is not None
        assert isinstance(img, np.ndarray)
        assert img.shape == (150, 100, 3)  # Height, Width, Channels (BGR)

    def test_load_image_from_bytes_pil(self, sample_image_bytes):
        """Test loading image as PIL format."""
        img = load_image_from_bytes(sample_image_bytes, mode="pil")
        assert img is not None
        assert isinstance(img, Image.Image)
        assert img.size == (100, 150)  # Width, Height

    def test_load_image_from_bytes_invalid(self):
        """Test loading invalid image data."""
        img = load_image_from_bytes(b"invalid data", mode="cv2")
        assert img is None

    def test_convert_pil_to_cv2(self):
        """Test PIL to OpenCV conversion."""
        pil_img = Image.new("RGB", (100, 150), color=(255, 0, 0))
        cv2_img = convert_pil_to_cv2(pil_img)

        assert isinstance(cv2_img, np.ndarray)
        assert cv2_img.shape == (150, 100, 3)
        # Check BGR format (red in RGB becomes red in BGR)
        assert cv2_img[0, 0, 2] == 255  # Red channel
        assert cv2_img[0, 0, 0] == 0  # Blue channel

    def test_convert_cv2_to_pil(self):
        """Test OpenCV to PIL conversion."""
        cv2_img = np.zeros((150, 100, 3), dtype=np.uint8)
        cv2_img[:, :, 2] = 255  # Set red channel (BGR format)

        pil_img = convert_cv2_to_pil(cv2_img)
        assert isinstance(pil_img, Image.Image)
        assert pil_img.size == (100, 150)
        assert pil_img.getpixel((0, 0)) == (255, 0, 0)  # RGB format

    def test_resize_image_with_aspect_ratio_cv2(self):
        """Test aspect ratio preserving resize for OpenCV image."""
        img = np.zeros((200, 100, 3), dtype=np.uint8)
        resized = resize_image_with_aspect_ratio(img, 50)

        # Height is larger, so it becomes max_size
        assert resized.shape == (50, 25, 3)

    def test_resize_image_with_aspect_ratio_pil(self):
        """Test aspect ratio preserving resize for PIL image."""
        img = Image.new("RGB", (100, 200))
        resized = resize_image_with_aspect_ratio(img, 50)

        assert resized.size == (25, 50)

    def test_resize_image_to_square_crop(self):
        """Test square resize with cropping."""
        # Test with OpenCV
        cv2_img = np.zeros((200, 100, 3), dtype=np.uint8)
        resized_cv2 = resize_image_to_square(cv2_img, 50, crop=True)
        assert resized_cv2.shape == (50, 50, 3)

        # Test with PIL
        pil_img = Image.new("RGB", (100, 200))
        resized_pil = resize_image_to_square(pil_img, 50, crop=True)
        assert resized_pil.size == (50, 50)

    def test_resize_image_to_square_padding(self):
        """Test square resize with padding."""
        # Test with OpenCV
        cv2_img = np.zeros((200, 100, 3), dtype=np.uint8)
        cv2_img[:, :] = [255, 0, 0]  # Blue image
        resized_cv2 = resize_image_to_square(cv2_img, 50, crop=False)
        assert resized_cv2.shape == (50, 50, 3)
        # Check padding is white
        assert np.all(resized_cv2[0, 0] == [255, 255, 255])

        # Test with PIL
        pil_img = Image.new("RGB", (100, 200), color=(0, 0, 255))
        resized_pil = resize_image_to_square(pil_img, 50, crop=False)
        assert resized_pil.size == (50, 50)
        # Check padding is white
        assert resized_pil.getpixel((0, 0)) == (255, 255, 255)

    def test_ensure_rgb_format(self, sample_rgba_image_bytes):
        """Test RGB format conversion."""
        img = Image.open(io.BytesIO(sample_rgba_image_bytes))
        assert img.mode == "RGBA"

        rgb_img = ensure_rgb_format(img)
        assert rgb_img.mode == "RGB"
        assert rgb_img.size == img.size

    def test_save_image_to_bytes(self):
        """Test saving image to bytes."""
        # Test with PIL image
        pil_img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        bytes_data = save_image_to_bytes(pil_img, format="JPEG", quality=90)
        assert len(bytes_data) > 0

        # Verify it can be loaded back
        reloaded = Image.open(io.BytesIO(bytes_data))
        assert reloaded.size == (100, 100)

        # Test with OpenCV image
        cv2_img = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2_img[:, :, 2] = 255  # Red in BGR
        bytes_data = save_image_to_bytes(cv2_img, format="PNG")
        assert len(bytes_data) > 0

    def test_get_image_dimensions(self):
        """Test getting image dimensions."""
        # Test with OpenCV
        cv2_img = np.zeros((150, 100, 3), dtype=np.uint8)
        width, height = get_image_dimensions(cv2_img)
        assert width == 100
        assert height == 150

        # Test with PIL
        pil_img = Image.new("RGB", (100, 150))
        width, height = get_image_dimensions(pil_img)
        assert width == 100
        assert height == 150
