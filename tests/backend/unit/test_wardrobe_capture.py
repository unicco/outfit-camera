
import pytest

pytest.skip("レガシー衣類抽出テストは現在のユニット検証から除外", allow_module_level=True)

#!/usr/bin/env python3
"""Test script for wardrobe capture functionality"""

import json
import os
import sys

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pytest
import requests


@pytest.mark.skip(reason="Requires running camera service on port 8001")
def test_wardrobe_capture_api():
    """Test wardrobe capture via API endpoints."""
    base_url = "http://localhost:8001"

    print("Testing Wardrobe Capture API...")

    # 1. Check health
    print("\n1. Checking camera service health...")
    response = requests.get(f"{base_url}/health")
    print(f"Health check: {response.json()}")

    # 2. Set capture mode to wardrobe
    print("\n2. Setting capture mode to wardrobe_item...")
    response = requests.post(f"{base_url}/mode/wardrobe_item")
    print(f"Mode change: {response.json()}")

    # 3. Start wardrobe session
    print("\n3. Starting wardrobe capture session...")
    response = requests.post(f"{base_url}/wardrobe/start-session")
    session_data = response.json()
    print(f"Session start: {session_data}")
    session_id = session_data.get("session_id")

    # 4. Capture several wardrobe items
    test_items = [
        {
            "item_type": "top",
            "item_name": "Blue Cotton T-Shirt",
            "brand": "TestBrand",
            "color": "Blue",
            "tags": ["casual", "summer", "cotton"],
        },
        {
            "item_type": "bottom",
            "item_name": "Black Jeans",
            "brand": "TestDenim",
            "color": "Black",
            "tags": ["casual", "denim", "everyday"],
        },
        {
            "item_type": "outerwear",
            "item_name": "Gray Hoodie",
            "brand": "TestWear",
            "color": "Gray",
            "tags": ["casual", "warm", "hoodie"],
        },
    ]

    print("\n4. Capturing wardrobe items...")
    for i, item in enumerate(test_items, 1):
        print(f"\n   Item {i}/{len(test_items)}: {item['item_name']}")
        response = requests.post(f"{base_url}/wardrobe/capture-item", json=item)
        result = response.json()
        print(f"   Capture result: {result.get('status')}")
        if result.get("status") == "success":
            print(f"   Item ID: {result.get('item_id')}")
            print(f"   Filename: {result.get('filename')}")

    # 5. Check session status
    print("\n5. Checking session status...")
    response = requests.get(f"{base_url}/wardrobe/session-status")
    status = response.json()
    print(f"Session status: {status['status']}")
    if status.get("session"):
        print(f"Items captured: {len(status['session']['items'])}")

    # 6. End session
    print("\n6. Ending wardrobe session...")
    response = requests.post(f"{base_url}/wardrobe/end-session")
    end_result = response.json()
    print(f"Session end: {end_result}")

    # 7. Verify session files
    print("\n7. Verifying session files...")
    photos_dir = os.path.expanduser(os.environ.get("PHOTOS_DIR", "./photos"))
    wardrobe_dir = os.path.join(photos_dir, "wardrobe", session_id)
    if os.path.exists(wardrobe_dir):
        files = os.listdir(wardrobe_dir)
        print(f"Files in session directory: {len(files)}")
        for file in sorted(files):
            print(f"   - {file}")

        # Check session summary
        summary_path = os.path.join(wardrobe_dir, "session_summary.json")
        if os.path.exists(summary_path):
            with open(summary_path) as f:
                summary = json.load(f)
            print("\nSession summary:")
            print(f"   Session ID: {summary['id']}")
            print(f"   Started: {summary['started_at']}")
            print(f"   Ended: {summary['ended_at']}")
            print(f"   Total items: {len(summary['items'])}")

    # 8. Switch back to outfit mode
    print("\n8. Switching back to outfit mode...")
    response = requests.post(f"{base_url}/mode/outfit")
    print(f"Mode change: {response.json()}")

    print("\n✅ Wardrobe capture test completed!")


def main():
    """Main entry point for manual testing."""
    # Set environment for simulation mode
    os.environ["CAMERA_MODE"] = "hardware_simulation"

    print("Starting wardrobe capture test...")
    print("Make sure the camera service is running on port 8001")
    print("Run with: python camera/camera_service.py")
    print("-" * 50)

    # Import the actual test function without decorator

    try:
        # Call the test function directly
        print("Testing Wardrobe Capture API...")

        # Run the actual test logic...
        # (Copy the test logic here for manual execution)

    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to camera service on port 8001")
        print("Please start the camera service first:")
        print("  python camera/camera_service.py")
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
