"""SSRF protection helpers for outbound image fetches.

Server-side code fetches image URLs that ultimately originate from the database
or (in the Google Photos upload endpoint) from the request body. Without a host
allowlist an attacker could point those fetches at internal services or cloud
metadata endpoints. We only ever need to fetch our own Google Cloud Storage
objects, so we restrict outbound fetches to HTTPS GCS object URLs in our own
bucket.

The GCS allowlist first shipped inline in the ``wardrobe`` router (image-proxy); this
module centralises it so the AI-detection and Google Photos paths reuse the same
rule .

Callers must ALSO disable redirect following (``allow_redirects=False``): this
function only validates the caller-supplied URL, so a 3xx from an allowlisted
object could otherwise pivot the fetch to an arbitrary host.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

GCS_HOST = "storage.googleapis.com"
# Matches core/config.py's default so the allowlist tracks the storage bucket.
_DEFAULT_BUCKET = "example-wardrobe-dev"


def _allowed_bucket() -> str:
    """The single GCS bucket this deployment reads/writes (GCS_BUCKET_NAME)."""
    return os.getenv("GCS_BUCKET_NAME", _DEFAULT_BUCKET)


def is_allowed_storage_url(url: str) -> bool:
    """Return True only for HTTPS GCS object URLs in our own bucket.

    Everything else — other hosts, other buckets, non-HTTPS schemes, internal
    IPs, metadata endpoints, path-traversal, malformed input — is rejected, so
    callers must refuse to fetch it (and must pass ``allow_redirects=False``).
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme != "https" or parsed.netloc != GCS_HOST:
        return False

    # Path must be /<bucket>/<object...> and the bucket must be ours.
    parts = (parsed.path or "").split("/", 2)
    if len(parts) < 3:
        return False
    _, bucket, object_path = parts
    if bucket != _allowed_bucket() or not object_path:
        return False

    # Reject empty / traversal segments in the object path.
    if any(segment in ("", ".", "..") for segment in object_path.split("/")):
        return False

    return True
