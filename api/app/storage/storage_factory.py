import os
from typing import Optional

from .base_storage import BaseStorageHandler
from .gcs_storage import GCSStorageHandler
from .local_storage import LocalStorageHandler
from .google_photos_storage import GooglePhotosStorageHandler

# シングルトンインスタンスを保持
_storage_handler: Optional[BaseStorageHandler] = None
_google_photos_handler: Optional[GooglePhotosStorageHandler] = None


def get_storage_handler() -> BaseStorageHandler:
    """環境変数に基づいてストレージハンドラーを取得（シングルトン）."""
    global _storage_handler

    if _storage_handler is None:
        storage_type = os.getenv("STORAGE_TYPE", "local").lower()

        if storage_type == "gcs":
            _storage_handler = GCSStorageHandler()
        else:
            _storage_handler = LocalStorageHandler()

    return _storage_handler


def get_google_photos_handler() -> GooglePhotosStorageHandler:
    """Google Photos ストレージハンドラーを取得（シングルトン）."""
    global _google_photos_handler

    if _google_photos_handler is None:
        _google_photos_handler = GooglePhotosStorageHandler()

    return _google_photos_handler


def clear_handlers() -> None:
    """ハンドラーインスタンスをクリア（主にテスト用）."""
    global _storage_handler, _google_photos_handler
    _storage_handler = None
    _google_photos_handler = None
