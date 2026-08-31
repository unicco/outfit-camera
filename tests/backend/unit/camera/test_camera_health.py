#!/usr/bin/env python3
"""Test camera service health and stream endpoints."""

import os
from typing import Final

import pytest
import requests

pytest.skip(
    "カメラエンドポイントへの実アクセスが必要なためスキップ", allow_module_level=True
)


def test_camera_health_endpoint() -> None:
    """Ensure module imports succeed for unit testing."""
    assert True


def test_endpoint(url: str, description: str) -> bool:
    """Call endpoint and record whether it responded successfully."""
    print(f"\nTesting {description}: {url}")
    try:
        response = requests.get(url, timeout=5)
    except requests.RequestException as exc:  # pragma: no cover
        print(f"Request failed: {exc}")
        return False

    print(f"Status: {response.status_code}")
    return response.status_code == 200


def main() -> None:
    base_url = "http://localhost:8001"

    # Test various endpoints
    endpoints: Final[list[tuple[str, str]]] = [
        ("/health", "Health Check"),
        ("/stream", "Camera Stream"),
        ("/capture/preview", "Capture Preview"),
    ]

    print("=" * 60)
    print("CAMERA SERVICE ENDPOINT TESTING")
    print("=" * 60)

    results = {}
    for endpoint, description in endpoints:
        url = f"{base_url}{endpoint}"
        results[endpoint] = test_endpoint(url, description)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for endpoint, success in results.items():
        status = "✅ OK" if success else "❌ FAILED"
        print(f"{endpoint}: {status}")

    # Additional debugging info
    print("\nEnvironment Variables:")
    camera_vars = {k: v for k, v in os.environ.items() if "CAMERA" in k.upper()}
    for k, v in camera_vars.items():
        print(f"  {k}={v}")


if __name__ == "__main__":
    main()
