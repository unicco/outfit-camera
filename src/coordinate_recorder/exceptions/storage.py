"""ストレージ関連の例外クラス.

ファイルシステム、クラウドストレージ（GCS）に関連する例外を定義します。
"""

from typing import Optional, Any
from .base import CoordinateRecorderError


class StorageError(CoordinateRecorderError):
    """ストレージ操作の基底例外クラス.

    ローカルファイルシステムやクラウドストレージの操作エラーで使用されます。
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        if "error_code" not in kwargs:
            kwargs["error_code"] = "STORAGE_ERROR"
        super().__init__(message, **kwargs)


class FileNotFoundError(StorageError):
    """ファイルが見つからないエラー.

    要求されたファイルが存在しない場合に発生します。
    Python 組み込みの FileNotFoundError との混同を避けるため、
    CRFileNotFoundError としてエクスポートされます。
    """

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        storage_type: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        file_path: 見つからなかったファイルのパス
        storage_type: ストレージタイプ（local, gcs など）
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if file_path:
            details["file_path"] = file_path
        if storage_type:
            details["storage_type"] = storage_type
        kwargs["details"] = details
        kwargs["error_code"] = "FILE_NOT_FOUND"

        super().__init__(message, **kwargs)


class StorageConnectionError(StorageError):
    """ストレージ接続エラー.

    クラウドストレージへの接続に失敗した場合に発生します。
    """

    def __init__(
        self,
        message: str,
        service: Optional[str] = None,
        endpoint: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        service: ストレージサービス名（GCS, S3 など）
        endpoint: エンドポイント URL
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if service:
            details["service"] = service
        if endpoint:
            details["endpoint"] = endpoint
        kwargs["details"] = details
        kwargs["error_code"] = "STORAGE_CONNECTION_ERROR"

        super().__init__(message, **kwargs)


class StoragePermissionError(StorageError):
    """ストレージ権限エラー.

    ファイルやバケットへのアクセス権限がない場合に発生します。
    """

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        resource: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        operation: 実行しようとした操作（read, write, delete など）
        resource: アクセスしようとしたリソース
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if operation:
            details["operation"] = operation
        if resource:
            details["resource"] = resource
        kwargs["details"] = details
        kwargs["error_code"] = "STORAGE_PERMISSION_ERROR"

        super().__init__(message, **kwargs)
