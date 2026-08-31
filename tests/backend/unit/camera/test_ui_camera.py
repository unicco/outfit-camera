#!/usr/bin/env python3
"""Test UI camera integration."""

import os

import pytest
import requests


pytestmark = [pytest.mark.integration, pytest.mark.manual]


def _get_base_url() -> str:
    return os.environ.get("UI_BASE_URL", "http://localhost:3000")


def test_ui():
    base_url = _get_base_url()
    try:
        response = requests.get(f"{base_url}/", timeout=5)
    except requests.RequestException as exc:
        pytest.skip(f"UI service not reachable at {base_url}: {exc}")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_touchscreen():
    base_url = _get_base_url()
    try:
        response = requests.get(f"{base_url}/touchscreen", timeout=5)
    except requests.RequestException as exc:
        pytest.skip(f"Touchscreen UI not reachable at {base_url}: {exc}")

    assert response.status_code == 200


if __name__ == "__main__":
    print("=== UI Camera Integration Test ===")
    ui_ok = test_ui()
    touchscreen_ok = test_touchscreen()

    print("\nResults:")
    print(f"UI: {'✅' if ui_ok else '❌'}")
    print(f"Touchscreen: {'✅' if touchscreen_ok else '❌'}")

    print("\nDirect Access URLs:")
    print("UI: http://localhost:3000/")
    print("Touchscreen: http://localhost:3000/touchscreen")
    print("Camera Stream: http://localhost:8001/stream")
    print("Camera Health: http://localhost:8001/health")
