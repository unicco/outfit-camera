"""FastAPI dependency injection functions for services."""

import logging
from typing import TYPE_CHECKING, Annotated, Optional, Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from .path_setup import setup_sys_path
from .settings import Settings, get_settings
from .database import get_db as _get_db

# Setup sys.path for coordinate_recorder imports
setup_sys_path()

if TYPE_CHECKING:
    from .image_upload_service import ImageUploadService

logger = logging.getLogger(__name__)

# Cache for singleton services
_service_cache = {}


def get_image_upload_service() -> Optional["ImageUploadService"]:
    """Get singleton instance of ImageUploadService."""
    if "image_upload_service" not in _service_cache:
        try:
            from .image_upload_service import get_image_upload_service as _get_service

            _service_cache["image_upload_service"] = _get_service()
            logger.info("ImageUploadService dependency initialized")
        except Exception as e:
            logger.error(f"Failed to initialize ImageUploadService: {e}")
            _service_cache["image_upload_service"] = None  # type: ignore[assignment]

    return _service_cache["image_upload_service"]


# Dependency type aliases for cleaner code
SettingsDep = Annotated[Settings, Depends(get_settings)]
ImageUploadServiceDep = Annotated[
    Optional["ImageUploadService"], Depends(get_image_upload_service)
]


def cleanup_dependencies() -> None:
    """Clean up all cached dependencies."""
    global _service_cache
    _service_cache.clear()
    logger.info("All dependencies cleaned up")


def get_db() -> Generator[Session, None, None]:
    """Yield database session for FastAPI dependencies."""
    yield from _get_db()
