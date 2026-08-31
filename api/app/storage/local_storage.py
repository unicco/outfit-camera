import os
import json
import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from .base_storage import BaseStorageHandler

logger = logging.getLogger(__name__)


class LocalStorageHandler(BaseStorageHandler):
    """ローカルストレージハンドラー."""

    def __init__(self) -> None:
        self.api_url = os.getenv("API_URL", "http://localhost:8000")
        self.base_path = Path(os.getenv("DATA_DIR", "./data"))

    def get_photo_url(self, photo_id: str) -> str:
        """ローカル写真の URL を取得."""
        clean_photo_id = self.validate_photo_id(photo_id)
        return f"{self.api_url}/photos/{clean_photo_id}"

    def get_file_url(self, photo_uuid: str) -> str:
        """ローカルファイルの URL を取得（データベース保存用）."""
        return f"{self.api_url}/photos/{photo_uuid}"

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

    def upload_file(
        self, local_path: str, remote_path: str, content_type: Optional[str] = None
    ) -> str:
        """ファイルをローカルストレージにコピー."""
        try:
            full_path = self.base_path / remote_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, full_path)
            return str(full_path)
        except Exception as e:
            logger.error(f"Failed to copy file to local storage: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload file")

    def upload_json(self, data: dict, remote_path: str) -> str:
        """JSON データをローカルストレージに保存."""
        try:
            full_path = self.base_path / remote_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return str(full_path)
        except Exception as e:
            logger.error(f"Failed to save JSON to local storage: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload JSON")

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """ローカルストレージからファイルをコピー."""
        try:
            full_path = self.base_path / remote_path
            if not full_path.exists():
                return False
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(full_path, local_path)
            return True
        except Exception as e:
            logger.error(f"Failed to copy file from local storage: {e}")
            return False

    def download_json(self, remote_path: str) -> Optional[dict]:
        """ローカルストレージから JSON データを読み込み."""
        try:
            full_path = self.base_path / remote_path
            if not full_path.exists():
                return None
            with open(full_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load JSON from local storage: {e}")
            return None

    def exists(self, remote_path: str) -> bool:
        """ローカルストレージ上のファイルの存在確認."""
        try:
            full_path = self.base_path / remote_path
            return full_path.exists()
        except Exception as e:
            logger.error(f"Failed to check file existence in local storage: {e}")
            return False
