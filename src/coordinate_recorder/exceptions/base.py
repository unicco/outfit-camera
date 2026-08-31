"""基底例外クラス.

Coordinate Recorder プロジェクトのすべての例外クラスの基底となるクラスを定義します。
統一的なエラー情報管理とログ記録のための基盤を提供します。
"""

from typing import Any, Dict, Optional


class CoordinateRecorderError(Exception):
    """Coordinate Recorder プロジェクトの基底例外クラス.

    すべてのカスタム例外はこのクラスを継承します。
    エラーコード、詳細情報、および原因となった例外を管理します。
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        """Args:
        message: エラーメッセージ
        error_code: エラーコード（ログやトラブルシューティング用）
        details: 追加のコンテキスト情報
        cause: 原因となった例外.

        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.cause = cause

    def __str__(self) -> str:
        """エラーメッセージの文字列表現."""
        parts = [self.message]
        if self.error_code:
            parts.append(f"[{self.error_code}]")
        if self.details:
            parts.append(f"Details: {self.details}")
        if self.cause:
            parts.append(f"Caused by: {type(self.cause).__name__}: {str(self.cause)}")
        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """例外情報を辞書形式で返す（API レスポンス用）."""
        return {
            "error": type(self).__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }


class ValidationError(CoordinateRecorderError):
    """データ検証エラー.

    入力データの検証に失敗した場合に発生します。
    フォーム入力、API パラメータ、ファイル形式などの検証で使用されます。
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Args:
        message: エラーメッセージ
        field: 検証に失敗したフィールド名
        value: 検証に失敗した値
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        kwargs["details"] = details

        # エラーコードのデフォルト設定
        if "error_code" not in kwargs:
            kwargs["error_code"] = "VALIDATION_ERROR"

        super().__init__(message, **kwargs)


class ProcessingError(CoordinateRecorderError):
    """処理実行時エラー.

    ビジネスロジックの実行中に発生するエラーです。
    予期しない状態、処理の失敗、タイムアウトなどで使用されます。
    """

    def __init__(
        self, message: str, operation: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        operation: 失敗した処理の名前
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if operation:
            details["operation"] = operation
        kwargs["details"] = details

        # エラーコードのデフォルト設定
        if "error_code" not in kwargs:
            kwargs["error_code"] = "PROCESSING_ERROR"

        super().__init__(message, **kwargs)
