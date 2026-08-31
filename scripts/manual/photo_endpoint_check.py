#!/usr/bin/env python3
"""Test script for photo endpoint fixes."""

import sys
from pathlib import Path

import requests


def test_photo_endpoints():
    """Test both photo endpoints with real photo IDs."""
    # Get project root and photos directory
    project_root = Path(__file__).parent.parent
    photos_dir = project_root / "photos"

    print(f"📁 Testing photos from: {photos_dir}")

    if not photos_dir.exists():
        print(f"❌ Photos directory not found: {photos_dir}")
        return False

    # Get available photo files
    photo_files = list(photos_dir.glob("*.jpg"))
    if not photo_files:
        print(f"❌ No photo files found in {photos_dir}")
        return False

    print(f"📸 Found {len(photo_files)} photo files")

    # Test with first few photos
    test_photos = photo_files[:3]

    for photo_file in test_photos:
        photo_id = photo_file.stem  # filename without .jpg extension
        print(f"\n🔍 Testing photo ID: {photo_id}")

        # Test main.py endpoint: /photos/{photo_id}
        test_main_endpoint(photo_id)

        # Test api.py endpoint: /v2/photos/{photo_id}
        test_v2_endpoint(photo_id)

    return True


def test_main_endpoint(photo_id):
    """Test the main.py photo endpoint."""
    url = f"http://localhost:8000/photos/{photo_id}"

    try:
        response = requests.get(url, timeout=5, stream=True)
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if "image" in content_type:
                print(
                    f"✅ Main endpoint (/photos/{photo_id}): SUCCESS (Content-Type: {content_type})"
                )
            else:
                print(
                    f"⚠️ Main endpoint (/photos/{photo_id}): Unexpected content type: {content_type}"
                )
        else:
            print(f"❌ Main endpoint (/photos/{photo_id}): {response.status_code}")
            if response.status_code == 404:
                print(f"   Detail: {response.text[:100]}")
    except requests.exceptions.RequestException as e:
        print(f"🔗 Main endpoint (/photos/{photo_id}): Connection error - {e}")


def test_v2_endpoint(photo_id):
    """Test the api.py v2 photo endpoint."""
    url = f"http://localhost:8000/v2/photos/{photo_id}"

    try:
        response = requests.get(url, timeout=5, stream=True)
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if "image" in content_type:
                print(
                    f"✅ V2 endpoint (/v2/photos/{photo_id}): SUCCESS (Content-Type: {content_type})"
                )
            else:
                print(
                    f"⚠️ V2 endpoint (/v2/photos/{photo_id}): Unexpected content type: {content_type}"
                )
        else:
            print(f"❌ V2 endpoint (/v2/photos/{photo_id}): {response.status_code}")
            if response.status_code == 404:
                print(f"   Detail: {response.text[:100]}")
    except requests.exceptions.RequestException as e:
        print(f"🔗 V2 endpoint (/v2/photos/{photo_id}): Connection error - {e}")


def check_server_status():
    """Check if the API server is running."""
    try:
        response = requests.get("http://localhost:8000/healthz", timeout=5)
        if response.status_code == 200:
            print("✅ API server is running")
            return True
        else:
            print(f"❌ API server returned {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ API server is not accessible: {e}")
        return False


if __name__ == "__main__":
    print("🧪 Testing Photo Endpoint Fixes")
    print("=" * 50)

    if not check_server_status():
        print("\n💡 Please start the API server first:")
        print("   cd <repo root>")
        print("   ./scripts/start-dev.sh")
        sys.exit(1)

    success = test_photo_endpoints()

    print("\n" + "=" * 50)
    if success:
        print("🎉 Test completed!")
    else:
        print("❌ Test failed - check the issues above")
