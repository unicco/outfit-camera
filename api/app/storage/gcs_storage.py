import os
import json
import uuid
import logging
from typing import Optional

from fastapi import HTTPException

from .base_storage import BaseStorageHandler

logger = logging.getLogger(__name__)


class GCSStorageHandler(BaseStorageHandler):
    """Google Cloud Storage ハンドラー."""

    def __init__(self) -> None:
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "example-wardrobe-dev")
        self._client = None
        self._bucket = None

    def get_photo_url(self, photo_id: str) -> str:
        """GCS 写真の URL を取得."""
        clean_photo_id = self.validate_photo_id(photo_id)
        return f"https://storage.googleapis.com/{self.bucket_name}/photos/{clean_photo_id}.jpg"

    def get_file_url(self, photo_uuid: str) -> str:
        """GCS ファイルの URL を取得（データベース保存用）."""
        return (
            f"https://storage.googleapis.com/{self.bucket_name}/photos/{photo_uuid}.jpg"
        )

    def validate_photo_id(self, photo_id: str) -> str:
        """写真 ID を検証してクリーンアップ."""
        # Clean photo_id (remove extension if present)
        clean_photo_id = (
            photo_id.replace(".jpg", "").replace(".jpeg", "").replace(".png", "")
        )

        # Validate proper UUID format using uuid library
        try:
            uuid_obj = uuid.UUID(clean_photo_id)
            # Ensure it's a valid UUID string in lowercase with hyphens
            validated_uuid = str(uuid_obj).lower()
            return validated_uuid
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid UUID format for photo ID: {clean_photo_id}",
            )

    @property
    def client(self):
        """GCS クライアントを取得（遅延初期化）."""
        if self._client is None:
            try:
                from google.cloud import storage

                self._client = storage.Client()
                self._bucket = self._client.bucket(self.bucket_name)
            except Exception as e:
                logger.error(f"Failed to initialize GCS client: {e}")
                raise HTTPException(
                    status_code=500, detail="Failed to initialize storage client"
                )
        return self._client

    @property
    def bucket(self):
        """GCS バケットを取得."""
        if self._bucket is None:
            self.client  # クライアントを初期化
        return self._bucket

    def upload_file(
        self, local_path: str, remote_path: str, content_type: Optional[str] = None
    ) -> str:
        """ファイルを GCS にアップロード."""
        try:
            blob = self.bucket.blob(remote_path)
            blob.upload_from_filename(local_path, content_type=content_type)
            return f"gs://{self.bucket_name}/{remote_path}"
        except Exception as e:
            logger.error(f"Failed to upload file to GCS: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload file")

    def upload_json(self, data: dict, remote_path: str) -> str:
        """JSON データを GCS にアップロード."""
        try:
            blob = self.bucket.blob(remote_path)
            blob.upload_from_string(
                json.dumps(data, ensure_ascii=False, indent=2),
                content_type="application/json",
            )
            return f"gs://{self.bucket_name}/{remote_path}"
        except Exception as e:
            logger.error(f"Failed to upload JSON to GCS: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload JSON")

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """GCS からファイルをダウンロード."""
        try:
            blob = self.bucket.blob(remote_path)
            if not blob.exists():
                return False
            blob.download_to_filename(local_path)
            return True
        except Exception as e:
            logger.error(f"Failed to download file from GCS: {e}")
            return False

    def download_json(self, remote_path: str) -> Optional[dict]:
        """GCS から JSON データをダウンロード."""
        try:
            blob = self.bucket.blob(remote_path)
            if not blob.exists():
                return None
            content = blob.download_as_text()
            return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to download JSON from GCS: {e}")
            return None

    def exists(self, remote_path: str) -> bool:
        """GCS 上のファイルの存在確認."""
        try:
            blob = self.bucket.blob(remote_path)
            return blob.exists()
        except Exception as e:
            logger.error(f"Failed to check file existence in GCS: {e}")
            return False
