#!/usr/bin/env python3
"""Manual test script for API upload functionality."""

import os
import sys
import time
from datetime import datetime

import requests

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_api_endpoints():
    """Test various API endpoints for photo upload."""
    # Get API URL from environment or use default
    api_url = os.environ.get(
        "BACKEND_API_URL", os.environ.get("API_URL", "http://localhost:8000")
    )

    print(f"Testing API at: {api_url}")

    # Test endpoints
    endpoints = [
        f"{api_url}/health",
        f"{api_url}/api/v2/upload",
        f"{api_url}/docs",
    ]

    for endpoint in endpoints:
        try:
            # Test GET request first (except for upload endpoints)
            if "upload" not in endpoint:
                response = requests.get(endpoint, timeout=5)
                print(f"✓ GET {endpoint}: {response.status_code}")
            else:
                print(f"  {endpoint}: POST-only endpoint")
        except requests.exceptions.RequestException as e:
            print(f"✗ {endpoint}: {type(e).__name__}")

    print("\n" + "=" * 50 + "\n")


def test_photo_upload():
    """Test actual photo upload."""
    api_url = os.environ.get(
        "BACKEND_API_URL", os.environ.get("API_URL", "http://localhost:8000")
    )

    # Create a test image file
    test_file = f"test_photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    test_path = os.path.join("/tmp", test_file)

    # Create a simple test image (1x1 pixel)
    with open(test_path, "wb") as f:
        # Minimal JPEG header + data
        f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
        f.write(b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t")
        f.write(b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a")
        f.write(b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342")
        f.write(b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f")
        f.write(b"\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00")
        f.write(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xd9")

    print(f"Created test file: {test_path}")

    # Test upload endpoints
    endpoints = [
        f"{api_url}/api/v2/upload",
    ]

    for endpoint in endpoints:
        print(f"\nTesting upload to: {endpoint}")

        try:
            with open(test_path, "rb") as f:
                files = {"file": (test_file, f, "image/jpeg")}

                start_time = time.time()
                response = requests.post(endpoint, files=files, timeout=30)
                elapsed = time.time() - start_time

                print(f"Response status: {response.status_code}")
                print(f"Response time: {elapsed:.2f}s")

                if response.status_code == 200:
                    print("✓ Upload successful!")
                    try:
                        data = response.json()
                        print(f"Response data: {data}")
                    except Exception:
                        print(f"Response text: {response.text[:200]}")
                else:
                    print("✗ Upload failed")
                    print(f"Response: {response.text[:200]}")

        except requests.exceptions.RequestException as e:
            print(f"✗ Error: {type(e).__name__}: {e}")

    # Cleanup
    if os.path.exists(test_path):
        os.unlink(test_path)
        print("\nCleaned up test file")


def main():
    """Run all tests."""
    print("=" * 50)
    print("API Upload Test Script")
    print("=" * 50 + "\n")

    # Test 1: Check endpoints
    print("Test 1: Checking API endpoints")
    print("-" * 30)
    test_api_endpoints()

    # Test 2: Upload test
    print("Test 2: Testing photo upload")
    print("-" * 30)
    test_photo_upload()

    print("\n" + "=" * 50)
    print("Tests completed")


if __name__ == "__main__":
    main()
