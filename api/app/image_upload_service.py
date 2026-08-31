"""Image upload service for wardrobe management
GCS専用版 - ローカルストレージサポートを削除 (Issue #437).
"""

import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

from .upload_limits import MAX_IMAGE_UPLOAD_BYTES, read_upload_capped
from .utils.image_utils import (
    load_image_from_bytes,
    resize_image_to_square,
    save_image_to_bytes,
)


@dataclass
class ImageUploadResult:
    """画像アップロード結果クラス."""

    url: str


# Optional GCS import for cloud storage mode
try:
    from google.cloud import storage  # type: ignore[import-untyped]

    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False


class ImageUploadService:
    """Service for uploading wardrobe item images."""

    def __init__(self) -> None:
        """Initialize storage backend based on configuration."""
        import logging

        logger = logging.getLogger(__name__)

        self.storage_type = os.getenv("STORAGE_TYPE", "gcs").lower()
        logger.info(
            f"Initializing ImageUploadService with storage_type: {self.storage_type}"
        )

        # GCS専用初期化 (Issue #437: ローカルストレージサポート削除)
        if not GCS_AVAILABLE:
            logger.error("Google Cloud Storage package not installed")
            raise RuntimeError(
                "Google Cloud Storage is required but 'google-cloud-storage' package is not installed"
            )

        if self.storage_type != "gcs":
            logger.error(f"Invalid storage type: {self.storage_type}")
            raise ValueError(
                f"Only 'gcs' storage type is supported. Got: {self.storage_type}"
            )

        try:
            # Check required environment variables
            self.bucket_name = os.getenv("GCS_BUCKET_NAME")
            logger.info(f"GCS_BUCKET_NAME: {self.bucket_name}")

            if not self.bucket_name:
                logger.error("GCS_BUCKET_NAME environment variable not set")
                raise ValueError(
                    "GCS_BUCKET_NAME environment variable is required for cloud storage"
                )

            # Check credentials
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            logger.info(f"GOOGLE_APPLICATION_CREDENTIALS: {creds_path}")

            if creds_path:
                creds_exists = os.path.exists(creds_path)
                logger.info(f"Credentials file exists: {creds_exists}")
                if not creds_exists:
                    logger.warning(f"Credentials file not found at: {creds_path}")
            else:
                logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set")

            # Initialize GCS client
            try:
                logger.info("Initializing GCS client...")
                self.client = storage.Client()
                logger.info("GCS client initialized successfully")
            except Exception as e:
                logger.error(
                    f"Failed to initialize GCS client: {type(e).__name__}: {e}"
                )
                raise RuntimeError(
                    f"Failed to initialize GCS client - check authentication: {e}"
                )

            self.bucket = self.client.bucket(self.bucket_name)

            # Test GCS access
            try:
                logger.info(f"Testing access to bucket: {self.bucket_name}")
                bucket_exists = self.bucket.exists()
                logger.info(f"Bucket exists check result: {bucket_exists}")

                if not bucket_exists:
                    logger.error(
                        f"Bucket '{self.bucket_name}' does not exist or is not accessible"
                    )
                    raise ValueError(
                        f"Bucket '{self.bucket_name}' does not exist or is not accessible - check permissions"
                    )
                logger.info(
                    f"Successfully verified access to bucket: {self.bucket_name}"
                )
            except Exception as e:
                logger.error(f"Failed to access GCS bucket: {type(e).__name__}: {e}")
                raise RuntimeError(
                    f"Failed to access GCS bucket '{self.bucket_name}': {e}"
                )

        except Exception as e:
            # Re-raise with more detailed error context
            error_msg = f"GCS initialization failed: {e}"
            if "authentication" in str(e).lower() or "credentials" in str(e).lower():
                error_msg += (
                    " - Check GOOGLE_APPLICATION_CREDENTIALS or service account setup"
                )
            elif "permission" in str(e).lower():
                error_msg += " - Check bucket permissions and service account roles"

            logger.error(error_msg)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Full error details: {e}")

            # ストレージ設定の診断情報。認証ファイルのパスは漏らさず設定有無のみ記録する
            logger.error("Environment info:")
            logger.error(f"  - STORAGE_TYPE: {os.getenv('STORAGE_TYPE')}")
            logger.error(f"  - GCS_BUCKET_NAME: {os.getenv('GCS_BUCKET_NAME')}")
            logger.error(
                "  - GOOGLE_APPLICATION_CREDENTIALS: %s",
                "[SET]" if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") else "[NOT SET]",
            )
            logger.error(f"  - GCS_PROJECT_ID: {os.getenv('GCS_PROJECT_ID')}")

            raise RuntimeError(error_msg)

    def _generate_thumbnail(self, image_bytes: bytes, size: int) -> bytes:
        """Generate thumbnail from image bytes.

        Args:
            image_bytes: Original image as bytes
            size: Square size for thumbnail (e.g., 200 for 200x200)

        Returns:
            Thumbnail image as JPEG bytes

        """
        # Open image from bytes
        img = load_image_from_bytes(image_bytes, mode="pil")
        if img is None:
            raise ValueError("Failed to load image")

        # Resize to square (with crop)
        img = resize_image_to_square(img, size, crop=True)

        # Convert to JPEG bytes
        return save_image_to_bytes(img, format="JPEG", quality=60)

    async def upload_wardrobe_image(
        self, file: UploadFile, item_id: str
    ) -> Dict[str, Any]:
        """Upload a wardrobe item image with thumbnails.

        Args:
            file: The uploaded file
            item_id: The clothing item ID

        Returns:
            Dictionary containing image URLs and metadata

        """
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        extension = (
            file.filename.split(".")[-1].lower()
            if file.filename and "." in file.filename
            else "jpg"
        )

        # Validate file extension
        allowed_extensions = ["jpg", "jpeg", "png", "webp"]
        if extension not in allowed_extensions:
            extension = "jpg"  # Default to jpg

        # Read file contents (size-capped to prevent memory-exhaustion DoS)
        contents = await read_upload_capped(file, MAX_IMAGE_UPLOAD_BYTES)
        content_type = file.content_type or f"image/{extension}"

        # GCS専用アップロード (Issue #437)
        return await self._upload_to_gcs(
            contents, item_id, file_id, extension, content_type, file.filename
        )

    async def _upload_to_gcs(
        self,
        contents: bytes,
        item_id: str,
        file_id: str,
        extension: str,
        content_type: str,
        filename: Optional[str],
    ) -> Dict[str, Any]:
        """Upload to Google Cloud Storage."""
        # Upload original image
        blob_name = f"wardrobe/{item_id}/{file_id}.{extension}"
        blob = self.bucket.blob(blob_name)
        blob.upload_from_string(contents, content_type=content_type)

        # Generate and upload thumbnails
        thumbnails = {}
        for size in [200, 400]:
            try:
                thumb_blob_name = f"wardrobe/{item_id}/{file_id}_thumb_{size}.jpg"
                thumbnail_bytes = self._generate_thumbnail(contents, size)

                thumb_blob = self.bucket.blob(thumb_blob_name)
                thumb_blob.upload_from_string(
                    thumbnail_bytes, content_type="image/jpeg"
                )
                thumbnails[f"thumb_{size}"] = thumb_blob.public_url
            except Exception as e:
                print(f"Failed to generate {size}px thumbnail: {str(e)}")
                thumbnails[f"thumb_{size}"] = None

        return {
            "id": file_id,
            "original_url": blob.public_url,
            "thumbnails": thumbnails,
            "size": len(contents),
            "content_type": content_type,
            "filename": filename,
        }

    async def delete_wardrobe_images(self, item_id: str) -> None:
        """Delete all images for a wardrobe item.

        Args:
            item_id: The clothing item ID

        """
        # GCS専用削除 (Issue #437)
        prefix = f"wardrobe/{item_id}/"
        blobs = self.bucket.list_blobs(prefix=prefix)

        # Delete all blobs
        for blob in blobs:
            blob.delete()

    async def upload_multiple_images(
        self, files: List[UploadFile], item_id: str
    ) -> List[Dict[str, Any]]:
        """Upload multiple images for a wardrobe item.

        Args:
            files: List of uploaded files
            item_id: The clothing item ID

        Returns:
            List of dictionaries containing image URLs and metadata

        """
        uploaded_images = []

        for file in files:
            try:
                image_data = await self.upload_wardrobe_image(file, item_id)
                uploaded_images.append(image_data)
            except Exception as e:
                # Log error but continue with other files
                print(f"Failed to upload {file.filename}: {str(e)}")

        return uploaded_images

    def save_image(
        self, image_bytes: bytes, file_path: str, content_type: str = "image/jpeg"
    ) -> ImageUploadResult:
        """AI検出用の画像保存メソッド（crops、annotationsディレクトリ用）
        GCS専用版 - 常にGCS URLを返す（Issue #435, #437対応）.

        Args:
            image_bytes: 画像のバイトデータ
            file_path: 保存先パス（例: "crops/photo_id_item_0.jpg"）
            content_type: コンテンツタイプ

        Returns:
            ImageUploadResult: 保存されたファイルのGCS URL情報

        """
        try:
            # GCSに保存
            blob = self.bucket.blob(file_path)
            blob.upload_from_string(image_bytes, content_type=content_type)
            url = blob.public_url

            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"AI detection image saved to GCS: {url}")
            return ImageUploadResult(url)
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to save AI detection image to GCS: {e}")
            raise RuntimeError(f"GCS save failed: {e}")

    async def upload_photo(self, contents: bytes, photo_id: str) -> Dict[str, Any]:
        """Upload a photo (for touchscreen captures).

        Args:
            contents: Photo bytes
            photo_id: Photo UUID

        Returns:
            Dictionary containing photo URL and metadata

        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            # Upload to photos directory (not wardrobe)
            blob_name = f"photos/{photo_id}.jpg"
            logger.info(f"Uploading photo to GCS: {blob_name}")

            blob = self.bucket.blob(blob_name)
            # Add timeout to prevent SSL errors
            blob.upload_from_string(contents, content_type="image/jpeg", timeout=30)

            url = blob.public_url
            logger.info(f"Photo uploaded successfully to: {url}")

            return {
                "id": photo_id,
                "url": url,
                "size": len(contents),
                "content_type": "image/jpeg",
                "blob_name": blob_name,
            }
        except Exception as e:
            logger.error(
                f"Failed to upload photo {photo_id} to GCS: {type(e).__name__}: {e}"
            )
            raise


# Dependency injection function
_image_upload_service: Optional[ImageUploadService] = None


def get_image_upload_service() -> ImageUploadService:
    """Get or create the image upload service instance."""
    import logging

    logger = logging.getLogger(__name__)

    global _image_upload_service
    if _image_upload_service is None:
        logger.info("Creating new ImageUploadService instance")
        try:
            _image_upload_service = ImageUploadService()
            logger.info("ImageUploadService instance created successfully")
        except Exception as e:
            logger.error(
                f"Failed to create ImageUploadService: {type(e).__name__}: {e}"
            )
            raise
    else:
        logger.debug("Returning existing ImageUploadService instance")
    return _image_upload_service
