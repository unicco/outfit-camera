"""データ検証関連の例外クラス.

入力データの妥当性検証、形式チェックに関連する例外を定義します。
"""

from typing import Optional, Dict, Any, List, Union
from .base import ValidationError as BaseValidationError


class InvalidImageError(BaseValidationError):
    """無効な画像データエラー.

    画像データが期待する形式でない、破損している、
    またはサポートされていない形式の場合に発生します。
    """

    def __init__(
        self,
        message: str,
        image_format: Optional[str] = None,
        expected_formats: Optional[List[str]] = None,
        image_size: Optional[tuple] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        image_format: 実際の画像形式
        expected_formats: 期待される画像形式のリスト
        image_size: 画像サイズ（width, height）
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if image_format:
            details["image_format"] = image_format
        if expected_formats:
            details["expected_formats"] = expected_formats
        if image_size:
            details["image_size"] = {"width": image_size[0], "height": image_size[1]}
        kwargs["details"] = details
        kwargs["error_code"] = "INVALID_IMAGE"

        super().__init__(message, **kwargs)


class InvalidDataFormatError(BaseValidationError):
    """無効なデータ形式エラー.

    JSON、CSV などのデータ形式が期待する構造でない場合に発生します。
    """

    def __init__(
        self,
        message: str,
        data_type: Optional[str] = None,
        expected_schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        data_type: データタイプ（json, csv など）
        expected_schema: 期待されるスキーマ
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if data_type:
            details["data_type"] = data_type
        if expected_schema:
            details["expected_schema"] = expected_schema
        kwargs["details"] = details
        kwargs["error_code"] = "INVALID_DATA_FORMAT"

        super().__init__(message, **kwargs)


class RequiredFieldMissingError(BaseValidationError):
    """必須フィールド不足エラー.

    必須のフィールドやパラメータが提供されていない場合に発生します。
    """

    def __init__(
        self, message: str, missing_fields: Optional[List[str]] = None, **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        missing_fields: 不足しているフィールドのリスト
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if missing_fields:
            details["missing_fields"] = missing_fields
        kwargs["details"] = details
        kwargs["error_code"] = "REQUIRED_FIELD_MISSING"

        super().__init__(message, **kwargs)


class DataRangeError(BaseValidationError):
    """データ範囲エラー.

    数値や日付などのデータが有効な範囲外の場合に発生します。
    """

    def __init__(
        self,
        message: str,
        value: Optional[Union[int, float, str]] = None,
        min_value: Optional[Union[int, float, str]] = None,
        max_value: Optional[Union[int, float, str]] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        value: 実際の値
        min_value: 最小許容値
        max_value: 最大許容値
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if value is not None:
            details["value"] = str(value)
        if min_value is not None:
            details["min_value"] = str(min_value)
        if max_value is not None:
            details["max_value"] = str(max_value)
        kwargs["details"] = details
        kwargs["error_code"] = "DATA_RANGE_ERROR"

        super().__init__(message, value=value, **kwargs)
