"""統一例外モジュールのユニットテスト."""

from coordinate_recorder.exceptions import (
    CoordinateRecorderError,
    ValidationError,
    ProcessingError,
    InvalidImageError,
    ItemNotFoundError,
    ModelLoadError,
    StorageConnectionError,
    ColorExtractionError,
)


class TestBaseExceptions:
    """基底例外クラスのテスト."""

    def test_coordinate_recorder_error(self):
        """CoordinateRecorderError の基本機能をテスト."""
        # 基本的な例外
        exc = CoordinateRecorderError("Test error")
        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.error_code is None
        assert exc.details == {}
        assert exc.cause is None

        # 詳細情報付き
        exc = CoordinateRecorderError(
            "Test error",
            error_code="TEST_001",
            details={"key": "value"},
        )
        assert exc.error_code == "TEST_001"
        assert exc.details == {"key": "value"}
        assert "TEST_001" in str(exc)

        # 原因例外付き
        cause = ValueError("Original error")
        exc = CoordinateRecorderError("Wrapped error", cause=cause)
        assert exc.cause is cause
        assert "ValueError" in str(exc)

    def test_to_dict_method(self):
        """to_dict メソッドのテスト."""
        exc = CoordinateRecorderError(
            "Test error",
            error_code="TEST_001",
            details={"key": "value"},
        )
        result = exc.to_dict()

        assert result["error"] == "CoordinateRecorderError"
        assert result["message"] == "Test error"
        assert result["error_code"] == "TEST_001"
        assert result["details"] == {"key": "value"}

    def test_validation_error(self):
        """ValidationError の機能をテスト."""
        # フィールドと値を指定
        exc = ValidationError(
            "Invalid email format",
            field="email",
            value="not-an-email",
        )
        assert exc.details["field"] == "email"
        assert exc.details["value"] == "not-an-email"
        assert exc.error_code == "VALIDATION_ERROR"

    def test_processing_error(self):
        """ProcessingError の機能をテスト."""
        exc = ProcessingError(
            "Operation failed",
            operation="data_processing",
        )
        assert exc.details["operation"] == "data_processing"
        assert exc.error_code == "PROCESSING_ERROR"


class TestValidationExceptions:
    """検証関連例外のテスト."""

    def test_invalid_image_error(self):
        """InvalidImageError のテスト."""
        exc = InvalidImageError(
            "Unsupported image format",
            image_format="webp",
            expected_formats=["jpeg", "png"],
            image_size=(100, 100),
        )

        assert exc.error_code == "INVALID_IMAGE"
        assert exc.details["image_format"] == "webp"
        assert exc.details["expected_formats"] == ["jpeg", "png"]
        assert exc.details["image_size"]["width"] == 100
        assert exc.details["image_size"]["height"] == 100


class TestWardrobeExceptions:
    """ワードローブ関連例外のテスト."""

    def test_item_not_found_error(self):
        """ItemNotFoundError のテスト."""
        exc = ItemNotFoundError(
            "Item not found in database",
            item_id=123,
            search_criteria={"category": "tops", "color": "red"},
        )

        assert exc.error_code == "ITEM_NOT_FOUND"
        assert exc.details["item_id"] == 123
        assert exc.details["search_criteria"]["category"] == "tops"

    def test_color_extraction_error(self):
        """ColorExtractionError のテスト."""
        exc = ColorExtractionError(
            "Failed to extract colors",
            extraction_method="kmeans",
            image_info={"shape": (100, 100, 3)},
        )

        assert exc.error_code == "COLOR_EXTRACTION_ERROR"
        assert exc.details["extraction_method"] == "kmeans"
        assert exc.details["image_info"]["shape"] == (100, 100, 3)
        assert exc.details["operation"] == "color_extraction"


class TestDetectionExceptions:
    """検出関連例外のテスト."""

    def test_model_load_error(self):
        """ModelLoadError のテスト."""
        exc = ModelLoadError(
            "Failed to load YOLO model",
            model_path="/path/to/model.pt",
            model_type="YOLO",
        )

        assert exc.error_code == "MODEL_LOAD_ERROR"
        assert exc.details["model_path"] == "/path/to/model.pt"
        assert exc.details["model_type"] == "YOLO"


class TestStorageExceptions:
    """ストレージ関連例外のテスト."""

    def test_storage_connection_error(self):
        """StorageConnectionError のテスト."""
        exc = StorageConnectionError(
            "Failed to connect to GCS",
            service="GCS",
            endpoint="https://storage.googleapis.com",
        )

        assert exc.error_code == "STORAGE_CONNECTION_ERROR"
        assert exc.details["service"] == "GCS"
        assert exc.details["endpoint"] == "https://storage.googleapis.com"


class TestExceptionInheritance:
    """例外の継承関係のテスト."""

    def test_inheritance_chain(self):
        """すべての例外が正しく継承されているか確認."""
        # InvalidImageError は ValidationError を継承
        exc = InvalidImageError("Test")
        assert isinstance(exc, ValidationError)
        assert isinstance(exc, CoordinateRecorderError)
        assert isinstance(exc, Exception)

        # ColorExtractionError は ProcessingError を継承
        exc = ColorExtractionError("Test")
        assert isinstance(exc, ProcessingError)
        assert isinstance(exc, CoordinateRecorderError)

        # ModelLoadError は DetectionError を継承
        exc = ModelLoadError("Test")
        assert isinstance(exc, ProcessingError)
        assert isinstance(exc, CoordinateRecorderError)
