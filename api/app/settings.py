"""Application settings using Pydantic BaseModel for dependency injection.

This module is the single source of configuration for the API. The former
``app.config`` and ``app.core.config`` modules were merged here ;
directory constants (``PROJECT_ROOT``/``DATA_DIR``/``LOGS_DIR``) and the
``PHOTOS_DIR`` default now live on :class:`Settings`.
"""

import logging
import os
import warnings
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

# Project layout. settings.py lives at api/app/settings.py, so the repo root is
# three levels up; DATA_DIR / LOGS_DIR sit under api/app/ (matching the paths the
# removed core/config.py used).
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
LOGS_DIR = Path(__file__).parent / "logs"

# Load environment variables so get_settings() reads them (previously done as an
# import side effect of the removed core/config.py). database.py loads the same
# files independently; load_dotenv is idempotent so the duplication is harmless.
try:
    from dotenv import load_dotenv

    _env_common = PROJECT_ROOT / ".env.common"
    if _env_common.exists():
        load_dotenv(_env_common)
    load_dotenv(PROJECT_ROOT / ".env", override=True)
except ImportError:
    pass


# Define SecurityWarning for Python versions that don't have it
class SecurityWarning(UserWarning):
    """Security-related warning."""

    pass


class Settings(BaseModel):
    """Application settings with environment variable support."""

    # Database settings
    database_mode: str = "fallback"
    database_url: Optional[str] = None  # Should be set via environment variable
    db_echo: bool = False

    # API settings
    # 本番では効かない既定。systemd が `uvicorn --host 127.0.0.1` で起動する
    # （deploy/systemd/coordinate-api.service）。外部公開は Caddy 経由のみ
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8000
    log_level: str = "INFO"

    # CORS settings
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Storage settings
    storage_type: str = "gcs"
    # Default matches the removed core/config.py and the surviving
    # gcs_storage.py / url_safety.py os.getenv defaults, so an unset
    # GCS_BUCKET_NAME does not hard-fail startup (only an explicit empty does).
    gcs_bucket_name: Optional[str] = "example-wardrobe-dev"
    gcs_project_id: Optional[str] = None
    google_application_credentials: Optional[str] = None

    # Filesystem layout (merged from the removed core/config.py)
    photos_dir: str = os.path.expanduser(str(PROJECT_ROOT / "photos"))
    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    logs_dir: Path = LOGS_DIR
    api_url: str = "http://localhost:8000"

    # AI/ML settings
    disable_ai_features: bool = False
    disable_clothing_detection: bool = False
    skip_model_loading: bool = False
    enable_hybrid_matching: bool = True

    # Camera settings
    camera_service_url: str = "http://pi-camera.local:8001"

    # Memory optimization
    max_memory_mb: Optional[int] = None

    # Photo cleanup settings
    cleanup_enabled: bool = True
    photo_retention_days: int = 30

    # Weather / calendar integrations
    openweather_api_key: Optional[str] = None
    morning_location_lat: Optional[float] = None
    morning_location_lon: Optional[float] = None
    google_credentials_file: Optional[str] = None
    google_token_file: Optional[str] = None
    google_calendar_primary_id: Optional[str] = None
    google_calendar_extra_ids: Optional[List[str]] = None
    google_calendar_delegated_user: Optional[str] = None
    # 朝ブリーフ「今日会う人」用。Google Calendar の secret ICS URL（カンマ区切り）。
    # life-log と同じ ICS 経路を使う（個人カレンダーは service account で読めず、
    # OAuth は週次再認証の運用負担があるため）。
    calendar_ics_urls: Optional[List[str]] = None
    # ICS タイトルにこれらの語が含まれる予定は「今日会う人」から除外する（プライバシー）
    calendar_redact_title_keywords: Optional[List[str]] = None

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate database URL and reject insecure defaults.

        Local development legitimately uses the ``coordinate_pass`` default,
        so by default we only warn. Production sets
        ``REQUIRE_SECURE_DB_CREDENTIALS=true`` in its environment to turn the
        warning into a hard failure, so the API cannot silently boot with the
        default credentials . We gate on this dedicated flag
        rather than ``ENVIRONMENT=production`` because the latter also flips
        strict auth enforcement in auth.py / security.py.
        """
        if v and "coordinate_pass" in v:
            require_secure = (
                os.getenv("REQUIRE_SECURE_DB_CREDENTIALS", "false").lower() == "true"
            )
            if require_secure:
                raise ValueError(
                    "Default database credentials detected while "
                    "REQUIRE_SECURE_DB_CREDENTIALS=true. Set a strong password "
                    "in DATABASE_URL."
                )
            warnings.warn(
                "Default database credentials detected. Please use secure credentials.",
                SecurityWarning,
                stacklevel=2,
            )
        return v

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: List[str]) -> List[str]:
        """Validate CORS origins."""
        for origin in v:
            if origin == "*":
                warnings.warn(
                    "Wildcard CORS origin detected. This is a security risk in production.",
                    SecurityWarning,
                    stacklevel=2,
                )
        return v

    @field_validator("api_host")
    @classmethod
    def validate_api_host(cls, v: str) -> str:
        """Validate API host configuration."""
        if v == "0.0.0.0" and os.getenv("ENVIRONMENT") == "production":  # noqa: S104
            warnings.warn(
                "Binding to 0.0.0.0 in production. Consider using a specific IP address.",
                SecurityWarning,
                stacklevel=2,
            )
        return v

    @property
    def db_enabled(self) -> bool:
        """Whether a database URL is configured.

        Equivalent to the removed ``core.config.DB_ENABLED``
        (``bool(os.getenv("DATABASE_URL"))``).
        """
        return bool(self.database_url)

    @staticmethod
    def _resolve_database_mode() -> str:
        """Read DATABASE_MODE, accepting the legacy ``optional`` alias.

        ``optional`` was the old ``app.config`` default but was rejected by
        ``Settings`` . We now normalize it to ``fallback`` and warn
        instead of crashing every ``get_settings()`` code path.
        """
        mode = os.getenv("DATABASE_MODE", "fallback").strip().lower()
        if mode == "optional":
            message = (
                "DATABASE_MODE=optional is deprecated; treating it as 'fallback'. "
                "Update the environment to 'fallback' to silence this warning."
            )
            warnings.warn(message, UserWarning, stacklevel=2)
            logger.warning(message)
            mode = "fallback"
        return mode

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        return cls(
            database_mode=cls._resolve_database_mode(),
            database_url=os.getenv("DATABASE_URL"),
            db_echo=os.getenv("DB_ECHO", "false").lower() == "true",
            api_host=os.getenv("API_HOST", "0.0.0.0"),  # noqa: S104
            api_port=int(os.getenv("API_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            cors_origins=[
                origin.strip()
                for origin in os.getenv(
                    "CORS_ORIGINS", "http://localhost:3000,http://localhost:8080"
                ).split(",")
                if origin.strip()
            ],
            storage_type=os.getenv("STORAGE_TYPE", "gcs").lower(),
            gcs_bucket_name=os.getenv("GCS_BUCKET_NAME", "example-wardrobe-dev"),
            gcs_project_id=os.getenv("GCS_PROJECT_ID"),
            google_application_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            photos_dir=os.path.expanduser(
                os.getenv("PHOTOS_DIR", str(PROJECT_ROOT / "photos"))
            ),
            api_url=os.getenv("API_URL", "http://localhost:8000"),
            disable_ai_features=os.getenv("DISABLE_AI_FEATURES", "false").lower()
            == "true",
            disable_clothing_detection=os.getenv(
                "DISABLE_CLOTHING_DETECTION", "false"
            ).lower()
            == "true",
            skip_model_loading=os.getenv("SKIP_MODEL_LOADING", "false").lower()
            == "true",
            enable_hybrid_matching=os.getenv("ENABLE_HYBRID_MATCHING", "true").lower()
            == "true",
            camera_service_url=os.getenv(
                "CAMERA_SERVICE_URL", "http://pi-camera.local:8001"
            ),
            max_memory_mb=(
                int(max_memory_str)
                if (max_memory_str := os.getenv("MAX_MEMORY_MB"))
                else None
            ),
            cleanup_enabled=os.getenv("CLEANUP_ENABLED", "true").lower() == "true",
            photo_retention_days=int(os.getenv("PHOTO_RETENTION_DAYS", "30")),
            openweather_api_key=os.getenv("OPENWEATHER_API_KEY"),
            morning_location_lat=_parse_float(os.getenv("MORNING_LOCATION_LAT")),
            morning_location_lon=_parse_float(os.getenv("MORNING_LOCATION_LON")),
            google_credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE"),
            google_token_file=os.getenv("GOOGLE_TOKEN_FILE"),
            google_calendar_primary_id=os.getenv("GOOGLE_CALENDAR_PRIMARY_ID"),
            google_calendar_extra_ids=_parse_list(
                os.getenv("GOOGLE_CALENDAR_EXTRA_IDS", "")
            ),
            google_calendar_delegated_user=os.getenv("GOOGLE_CALENDAR_DELEGATED_USER"),
            calendar_ics_urls=_parse_list(os.getenv("CALENDAR_ICS_URLS", "")),
            calendar_redact_title_keywords=_parse_list(
                os.getenv("CALENDAR_REDACT_TITLE_KEYWORDS", "")
            ),
        )

    def validate_database_mode(self) -> None:
        """Validate database mode setting."""
        valid_modes = ["required", "fallback", "fileonly"]
        if self.database_mode not in valid_modes:
            raise ValueError(
                f"Invalid DATABASE_MODE: {self.database_mode}. "
                f"Must be one of: {', '.join(valid_modes)}"
            )

        # Validate database_url for required mode
        if self.database_mode == "required" and not self.database_url:
            raise ValueError(
                "DATABASE_URL must be set when DATABASE_MODE is 'required'"
            )

        # Additional validation for storage configuration
        if self.storage_type == "gcs" and not self.gcs_bucket_name:
            warnings.warn(
                "GCS storage type selected but GCS_BUCKET_NAME is not set", UserWarning
            )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance (singleton pattern)."""
    settings = Settings.from_env()
    settings.validate_database_mode()
    return settings


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_list(value: str) -> Optional[List[str]]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None
