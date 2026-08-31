"""AI/画像検出関連の例外クラス.

物体検出、画像認識、モデル処理に関連する例外を定義します。
"""

from typing import Optional, Dict, Any, List
from .base import ProcessingError


class DetectionError(ProcessingError):
    """検出処理の基底例外クラス.

    AI モデルによる検出処理全般のエラーで使用されます。
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        if "error_code" not in kwargs:
            kwargs["error_code"] = "DETECTION_ERROR"
        super().__init__(message, **kwargs)


class ModelLoadError(DetectionError):
    """モデル読み込みエラー.

    AI モデルの読み込みに失敗した場合に発生します。
    """

    def __init__(
        self,
        message: str,
        model_path: Optional[str] = None,
        model_type: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        model_path: モデルファイルのパス
        model_type: モデルの種類（Gemini, ResNet など）
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if model_path:
            details["model_path"] = model_path
        if model_type:
            details["model_type"] = model_type
        kwargs["details"] = details
        kwargs["error_code"] = "MODEL_LOAD_ERROR"

        super().__init__(message, **kwargs)


class InferenceError(DetectionError):
    """推論実行エラー.

    モデルの推論実行中に発生するエラーです。
    """

    def __init__(
        self, message: str, image_info: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        image_info: 処理中の画像情報（サイズ、形式など）
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if image_info:
            details["image_info"] = image_info
        kwargs["details"] = details
        kwargs["error_code"] = "INFERENCE_ERROR"

        super().__init__(message, **kwargs)


class InvalidDetectionResultError(DetectionError):
    """無効な検出結果エラー.

    検出結果が期待する形式でない、または無効な場合に発生します。
    """

    def __init__(
        self,
        message: str,
        detected_items: Optional[List[Dict[str, Any]]] = None,
        expected_format: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """Args:
        message: エラーメッセージ
        detected_items: 検出されたアイテムのリスト
        expected_format: 期待される形式の説明
        **kwargs: 基底クラスの追加パラメータ.

        """
        details = kwargs.get("details", {})
        if detected_items is not None:
            details["detected_items_count"] = len(detected_items)
            # 最初の数件のみを詳細に含める
            details["sample_items"] = detected_items[:3] if detected_items else []
        if expected_format:
            details["expected_format"] = expected_format
        kwargs["details"] = details
        kwargs["error_code"] = "INVALID_DETECTION_RESULT"

        super().__init__(message, **kwargs)
