from abc import ABC, abstractmethod
from typing import Optional


class BaseStorageHandler(ABC):
    """ストレージハンドラーの基底クラス."""

    @abstractmethod
    def get_photo_url(self, photo_id: str) -> str:
        """写真の URL を取得."""
        pass

    @abstractmethod
    def get_file_url(self, photo_uuid: str) -> str:
        """ファイルの URL を取得（データベース保存用）."""
        pass

    @abstractmethod
    def validate_photo_id(self, photo_id: str) -> str:
        """写真 ID を検証してクリーンアップ."""
        pass

    @abstractmethod
    def upload_file(
        self, local_path: str, remote_path: str, content_type: Optional[str] = None
    ) -> str:
        """ファイルをアップロード."""
        pass

    @abstractmethod
    def upload_json(self, data: dict, remote_path: str) -> str:
        """JSON データをアップロード."""
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> bool:
        """ファイルをダウンロード."""
        pass

    @abstractmethod
    def download_json(self, remote_path: str) -> Optional[dict]:
        """JSON データをダウンロード."""
        pass

    @abstractmethod
    def exists(self, remote_path: str) -> bool:
        """ファイルの存在確認."""
        pass
