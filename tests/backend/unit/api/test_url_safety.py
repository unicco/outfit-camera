"""Tests for the SSRF outbound-fetch allowlist .

The allowlist accepts only HTTPS Google Cloud Storage object URLs in this
deployment's own bucket (``GCS_BUCKET_NAME``, default ``example-wardrobe-dev``).
"""

from __future__ import annotations

import pytest

from app.url_safety import is_allowed_storage_url

BUCKET = "example-wardrobe-dev"  # matches the default GCS_BUCKET_NAME


@pytest.fixture(autouse=True)
def _pin_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the allowed bucket so tests don't depend on the ambient env."""
    monkeypatch.setenv("GCS_BUCKET_NAME", BUCKET)


@pytest.mark.parametrize(
    "url",
    [
        f"https://storage.googleapis.com/{BUCKET}/wardrobe/a.jpg",
        f"https://storage.googleapis.com/{BUCKET}/fullbody/2026-07-01/x.png",
        f"https://storage.googleapis.com/{BUCKET}/photos/uuid.jpg",
    ],
)
def test_allows_own_bucket_object_urls(url: str) -> None:
    assert is_allowed_storage_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        # Non-HTTPS
        f"http://storage.googleapis.com/{BUCKET}/obj.jpg",
        # Wrong host / look-alikes
        f"https://storage.googleapis.com.evil.com/{BUCKET}/obj.jpg",
        f"https://evil.com/{BUCKET}/obj.jpg",
        f"https://storage-googleapis.com/{BUCKET}/obj.jpg",
        # Other GCS bucket (host allowed but not ours) — the key #531 tightening
        "https://storage.googleapis.com/attacker-bucket/obj.jpg",
        "https://storage.googleapis.com/my.other-bucket/obj.jpg",
        # SSRF targets
        "https://169.254.169.254/latest/meta-data/",
        "http://localhost:8000/static/wardrobe/x.jpg",
        "http://127.0.0.1/admin",
        # Credential/userinfo trick pointing at another host
        f"https://storage.googleapis.com@evil.com/{BUCKET}/obj.jpg",
        # No object path
        "https://storage.googleapis.com/",
        f"https://storage.googleapis.com/{BUCKET}",
        f"https://storage.googleapis.com/{BUCKET}/",
        # Path traversal in object segment
        f"https://storage.googleapis.com/{BUCKET}/../secret.jpg",
        "https://storage.googleapis.com/../../etc/passwd",
        # Case / port variants (rejected: exact match)
        f"https://STORAGE.GOOGLEAPIS.COM/{BUCKET}/obj.jpg",
        f"https://storage.googleapis.com:443/{BUCKET}/obj.jpg",
        # Junk
        "",
        "not-a-url",
        "file:///etc/passwd",
    ],
)
def test_rejects_non_own_bucket_or_unsafe_urls(url: str) -> None:
    assert is_allowed_storage_url(url) is False


def test_respects_configured_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GCS_BUCKET_NAME", "prod-wardrobe")
    assert (
        is_allowed_storage_url("https://storage.googleapis.com/prod-wardrobe/x.jpg")
        is True
    )
    assert (
        is_allowed_storage_url(f"https://storage.googleapis.com/{BUCKET}/x.jpg")
        is False
    )


def test_rejects_non_string() -> None:
    assert is_allowed_storage_url(None) is False  # type: ignore[arg-type]
    assert is_allowed_storage_url(123) is False  # type: ignore[arg-type]
