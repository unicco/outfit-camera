"""ワードローブ機能関連の例外クラス.

衣類管理、色抽出、埋め込み生成など、ワードローブ特有の機能に関連する例外を定義します。
"""

from typing import Optional, Dict, Any
from .base import CoordinateRecorderError, ProcessingError


class WardrobeError(CoordinateRecorderError):
    """ワードローブ機能の基底例外クラス.

    ワードローブ管理に関連するすべてのエラーの基底クラスです。
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        if "error_code" not in kwargs:
            kwargs["error_code"] = "WARDROBE_ERROR"
        super().__init__(message, **kwargs)


class ItemNotFoundError(WardrobeError):
    """アイテムが見つからないエラー.

    指定された衣類アイテムがデータベースに存在しない場合に発生します。
    """

    def __init__(
        self,
        message: str,
        item_id: Optional[int] = None,
        search_criteria: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        item_id: 検索対象のアイテム ID
        search_criteria: 検索条件
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if item_id is not None:
            details["item_id"] = item_id
        if search_criteria:
            details["search_criteria"] = search_criteria
        kwargs["details"] = details
        kwargs["error_code"] = "ITEM_NOT_FOUND"

        super().__init__(message, **kwargs)


class DuplicateItemError(WardrobeError):
    """重複アイテムエラー.

    同じアイテムがすでに存在する場合に発生します。
    """

    def __init__(
        self,
        message: str,
        existing_item_id: Optional[int] = None,
        duplicate_criteria: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        existing_item_id: 既存アイテムの ID
        duplicate_criteria: 重複判定に使用した基準
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if existing_item_id is not None:
            details["existing_item_id"] = existing_item_id
        if duplicate_criteria:
            details["duplicate_criteria"] = duplicate_criteria
        kwargs["details"] = details
        kwargs["error_code"] = "DUPLICATE_ITEM"

        super().__init__(message, **kwargs)


class ColorExtractionError(ProcessingError):
    """色抽出処理のエラー.

    画像から色情報を抽出する際に発生するエラーです。
    """

    def __init__(
        self,
        message: str,
        extraction_method: Optional[str] = None,
        image_info: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        extraction_method: 使用した抽出方法（kmeans, histogram など）
        image_info: 画像情報
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if extraction_method:
            details["extraction_method"] = extraction_method
        if image_info:
            details["image_info"] = image_info
        kwargs["details"] = details
        kwargs["error_code"] = "COLOR_EXTRACTION_ERROR"
        kwargs["operation"] = "color_extraction"

        super().__init__(message, **kwargs)


class EmbeddingGenerationError(ProcessingError):
    """埋め込み生成エラー.

    Jina AI などの埋め込み生成サービスでエラーが発生した場合に使用されます。
    """

    def __init__(
        self,
        message: str,
        service: Optional[str] = None,
        model: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        service: 使用したサービス名（Jina AI など）
        model: 使用したモデル名
        input_data: 入力データの情報（センシティブでない部分）
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if service:
            details["service"] = service
        if model:
            details["model"] = model
        if input_data:
            # センシティブなデータは含めない
            details["input_type"] = input_data.get("type", "unknown")
            details["input_size"] = input_data.get("size")
        kwargs["details"] = details
        kwargs["error_code"] = "EMBEDDING_GENERATION_ERROR"
        kwargs["operation"] = "embedding_generation"

        super().__init__(message, **kwargs)
