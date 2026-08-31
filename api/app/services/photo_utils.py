"""Photo path/URL utilities.

Pure utility functions for photo ID normalization, path resolution,
URL normalization, date computation, and vector similarity.
"""

import os
from datetime import date, timedelta

import numpy as np
from fastapi import Request

from ..storage.storage_factory import get_storage_handler
from ..utils.timezone_utils import jst_now


def _clean_photo_id(photo_id: str) -> str:
    """Normalize photo ID using the active storage handler."""
    handler = get_storage_handler()
    return handler.validate_photo_id(photo_id)


def _resolve_photo_image_path(photo_id: str, file_path: str | None) -> str | None:
    """Resolve a photo's stored path or URL to an accessible location."""
    handler = get_storage_handler()
    storage_type = os.getenv("STORAGE_TYPE", "local").lower()
    photos_dir = os.path.expanduser(os.getenv("PHOTOS_DIR", "./photos"))

    if file_path:
        if file_path.startswith(("http://", "https://")):
            return file_path

        if os.path.isabs(file_path):
            return file_path

        # Normalize relative paths
        relative_path = file_path
        if file_path.startswith("/static/photos/"):
            relative_path = file_path.replace("/static/photos/", "")
        elif file_path.startswith("/static/"):
            relative_path = file_path.replace("/static/", "")
        elif file_path.startswith("photos/"):
            relative_path = file_path.replace("photos/", "")
        else:
            relative_path = file_path.lstrip("/")

        absolute_candidate = os.path.join(photos_dir, relative_path)

        if os.path.exists(absolute_candidate):
            return absolute_candidate

        if storage_type == "gcs":
            clean_id = handler.validate_photo_id(photo_id)
            return handler.get_photo_url(clean_id)

        return absolute_candidate

    # No file_path stored
    if storage_type == "gcs":
        clean_id = handler.validate_photo_id(photo_id)
        return handler.get_photo_url(clean_id)

    return os.path.join(photos_dir, f"{photo_id}.jpg")


def normalize_photo_url(file_path: str, request: Request) -> str:
    """Convert file_path to proper URL for frontend consumption."""
    if not file_path:
        return ""

    # If already a full URL (GCS), return as-is
    if file_path.startswith(("http://", "https://")):
        return file_path

    # If relative path starting with 'photos/', convert to API server URL
    if file_path.startswith("photos/"):
        base_url = f"{request.url.scheme}://{request.url.netloc}"
        return f"{base_url}/{file_path}"

    # If starts with '/static/', convert to API server URL
    if file_path.startswith("/static/"):
        base_url = f"{request.url.scheme}://{request.url.netloc}"
        return f"{base_url}{file_path}"

    # Default: return as-is
    return file_path


def get_effective_date() -> date:
    """Get the effective date based on 7AM cutoff."""
    now = jst_now()
    if now.hour < 7:
        # Before 7AM, use previous day
        return (now - timedelta(days=1)).date()
    return now.date()


def cosine_similarity_numpy(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors using numpy."""
    a_norm = a / np.linalg.norm(a)
    b_norm = b / np.linalg.norm(b)
    return np.dot(a_norm, b_norm.T)
