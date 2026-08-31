"""Coordinate Recorder 統一例外モジュール.

プロジェクト全体で使用される例外クラスを提供します。
一貫したエラーハンドリングとログ記録を実現します。

Example:
    >>> from coordinate_recorder.exceptions import ValidationError, ItemNotFoundError
    >>> raise ValidationError("Invalid data format", field="email")

"""

from .base import (
    CoordinateRecorderError,
    ValidationError,
    ProcessingError,
)

from .detection import (
    DetectionError,
    ModelLoadError,
    InferenceError,
    InvalidDetectionResultError,
)

from .storage import (
    StorageError,
    FileNotFoundError as CRFileNotFoundError,  # Python組み込みとの混同を避けるため
    StorageConnectionError,
    StoragePermissionError,
)

from .validation import (
    InvalidImageError,
    InvalidDataFormatError,
    RequiredFieldMissingError,
    DataRangeError,
)

from .wardrobe import (
    WardrobeError,
    ItemNotFoundError,
    DuplicateItemError,
    ColorExtractionError,
    EmbeddingGenerationError,
)

__all__ = [
    # 基底クラス
    "CoordinateRecorderError",
    "ValidationError",
    "ProcessingError",
    # 検出関連
    "DetectionError",
    "ModelLoadError",
    "InferenceError",
    "InvalidDetectionResultError",
    # ストレージ関連
    "StorageError",
    "CRFileNotFoundError",
    "StorageConnectionError",
    "StoragePermissionError",
    # 検証関連
    "InvalidImageError",
    "InvalidDataFormatError",
    "RequiredFieldMissingError",
    "DataRangeError",
    # ワードローブ関連
    "WardrobeError",
    "ItemNotFoundError",
    "DuplicateItemError",
    "ColorExtractionError",
    "EmbeddingGenerationError",
]
