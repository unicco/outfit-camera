"""Test helpers for dependency injection overrides."""


class MockSettings:
    """Mock settings for testing."""

    def __init__(self, **kwargs):
        # Default test settings
        self.database_mode = kwargs.get("database_mode", "fileonly")
        self.database_url = kwargs.get("database_url", "sqlite:///test.db")
        self.db_echo = kwargs.get("db_echo", False)
        self.api_host = kwargs.get("api_host", "127.0.0.1")
        self.api_port = kwargs.get("api_port", 8000)
        self.log_level = kwargs.get("log_level", "DEBUG")
        self.cors_origins = kwargs.get("cors_origins", ["http://localhost:3000"])
        self.storage_type = kwargs.get("storage_type", "filesystem")
        self.gcs_bucket_name = kwargs.get("gcs_bucket_name", None)
        self.gcs_project_id = kwargs.get("gcs_project_id", None)
        self.google_application_credentials = kwargs.get(
            "google_application_credentials", None
        )
        self.disable_ai_features = kwargs.get("disable_ai_features", True)
        self.disable_clothing_detection = kwargs.get("disable_clothing_detection", True)
        self.camera_service_url = kwargs.get("camera_service_url", "http://test:8001")
        self.max_memory_mb = kwargs.get("max_memory_mb", None)

    def validate_database_mode(self):
        """Mock validation - always passes."""
        pass


class MockImageUploadService:
    """Mock ImageUploadService for testing."""

    def __init__(self, **kwargs):
        self.bucket_name = kwargs.get("bucket_name", "test-bucket")

    async def upload_image(self, file_data, filename):
        """Mock upload method."""
        return f"https://storage.googleapis.com/{self.bucket_name}/{filename}"

    def get_bucket_name(self):
        """Mock bucket getter."""
        return self.bucket_name


def override_get_settings(**kwargs) -> MockSettings:
    """Override for get_settings dependency."""
    return MockSettings(**kwargs)


def override_get_image_upload_service(**kwargs) -> MockImageUploadService:
    """Override for get_image_upload_service dependency."""
    return MockImageUploadService(**kwargs)


