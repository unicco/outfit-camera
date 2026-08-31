#!/usr/bin/env python3
"""Test script for manual capture workflow."""

import json
import os
import sys
import time

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import pytest
import requests


@pytest.mark.skip(reason="Requires running camera service on port 8001")
def test_manual_workflow_api():
    """Test manual capture workflow via API."""
    base_url = "http://localhost:8001"

    print("Testing Manual Capture Workflow...")
    print("-" * 50)

    # 1. Check camera service
    print("\n1. Checking camera service...")
    try:
        response = requests.get(f"{base_url}/health")
        health_data = response.json()
        print(f"   Status: {health_data['status']}")
        print(f"   Camera mode: {health_data['camera_mode']}")
        print(f"   Capture mode: {health_data['capture_mode']}")
    except requests.exceptions.ConnectionError:
        print("   ❌ Camera service is not running!")
        print("   Please start: python camera/camera_service.py")
        return

    # 2. Set wardrobe mode
    print("\n2. Setting wardrobe capture mode...")
    response = requests.post(f"{base_url}/mode/wardrobe_item")
    print(f"   Response: {response.json()}")

    # 3. Start session
    print("\n3. Starting capture session...")
    response = requests.post(f"{base_url}/wardrobe/start-session")
    session_data = response.json()
    session_id = session_data.get("session_id")
    print(f"   Session ID: {session_id}")

    # 4. Simulate manual capture workflow
    print("\n4. Simulating manual captures...")

    # Test item 1: T-shirt
    print("\n   Capturing item 1: T-shirt")
    print("   - Countdown simulation: 3... 2... 1...")
    time.sleep(1)  # Simulate countdown

    item1 = {
        "item_type": "top",
        "item_name": "Striped Cotton T-Shirt",
        "brand": "TestBrand",
        "color": "Blue/White",
        "tags": ["casual", "striped", "cotton", "summer"],
    }
    response = requests.post(f"{base_url}/wardrobe/capture-item", json=item1)
    result1 = response.json()
    print(f"   - Result: {result1.get('status')}")
    if result1.get("status") == "success":
        print(f"   - Item ID: {result1.get('item_id')}")

    # Test item 2: Jeans
    print("\n   Capturing item 2: Jeans")
    print("   - Countdown simulation: 3... 2... 1...")
    time.sleep(1)

    item2 = {
        "item_type": "bottom",
        "item_name": "Dark Wash Jeans",
        "brand": "Denim Co",
        "color": "Dark Blue",
        "tags": ["casual", "denim", "everyday"],
    }
    response = requests.post(f"{base_url}/wardrobe/capture-item", json=item2)
    result2 = response.json()
    print(f"   - Result: {result2.get('status')}")
    if result2.get("status") == "success":
        print(f"   - Item ID: {result2.get('item_id')}")

    # Test item 3: Jacket
    print("\n   Capturing item 3: Jacket")
    print("   - User guidance simulation:")
    print("     • Place item on plain background")
    print("     • Ensure good lighting")
    print("     • Item should fill frame")
    print("   - Countdown simulation: 3... 2... 1...")
    time.sleep(1)

    item3 = {
        "item_type": "outerwear",
        "item_name": "Denim Jacket",
        "brand": "Urban Style",
        "color": "Light Blue",
        "tags": ["casual", "denim", "layering", "spring"],
    }
    response = requests.post(f"{base_url}/wardrobe/capture-item", json=item3)
    result3 = response.json()
    print(f"   - Result: {result3.get('status')}")
    if result3.get("status") == "success":
        print(f"   - Item ID: {result3.get('item_id')}")

    # 5. Check session status
    print("\n5. Checking session status...")
    response = requests.get(f"{base_url}/wardrobe/session-status")
    status = response.json()
    if status.get("session"):
        session_info = status["session"]
        print(f"   Session ID: {session_info['id']}")
        print(f"   Items captured: {len(session_info['items'])}")
        print(f"   Started at: {session_info['started_at']}")

        # Display captured items
        print("\n   Captured items:")
        for idx, item in enumerate(session_info["items"], 1):
            print(f"   {idx}. {item.get('item_name', 'Unnamed')} ({item['item_type']})")

    # 6. End session
    print("\n6. Ending capture session...")
    response = requests.post(f"{base_url}/wardrobe/end-session")
    end_data = response.json()
    print(f"   Status: {end_data.get('status')}")
    if end_data.get("session"):
        print(f"   Total items: {len(end_data['session']['items'])}")

    # 7. Verify files
    print("\n7. Verifying captured files...")
    photos_dir = os.path.expanduser(os.environ.get("PHOTOS_DIR", "./photos"))
    wardrobe_dir = os.path.join(photos_dir, "wardrobe", session_id)

    if os.path.exists(wardrobe_dir):
        files = os.listdir(wardrobe_dir)
        print(f"   Files created: {len(files)}")

        # Group files by type
        photos = [f for f in files if f.endswith(".jpg")]
        metadata_files = [f for f in files if f.endswith("_metadata.json")]

        print(f"   - Photos: {len(photos)}")
        print(f"   - Metadata files: {len(metadata_files)}")
        print(f"   - Session summary: {'session_summary.json' in files}")

        # Check metadata content
        if metadata_files:
            print("\n   Sample metadata content:")
            sample_metadata_file = os.path.join(wardrobe_dir, metadata_files[0])
            with open(sample_metadata_file) as f:
                metadata = json.load(f)
            print(f"   - Item: {metadata.get('item_name')}")
            print(f"   - Type: {metadata.get('item_type')}")
            print(f"   - Tags: {metadata.get('tags')}")

    print("\n✅ Manual capture workflow test completed!")


@pytest.mark.skip(reason="Integration test - requires manual execution")
def test_workflow_simulation():
    """Simulate the manual capture workflow experience."""
    print("\n" + "=" * 50)
    print("MANUAL CAPTURE WORKFLOW SIMULATION")
    print("=" * 50)

    print("\nThis simulates the user experience of the manual capture workflow:")

    print("\n1. User starts the wardrobe camera service")
    print("   $ python camera/camera_service.py")

    print("\n2. User interacts with the camera service API")
    print("   (Manual capture CLI has been removed - use API directly)")

    print("\n3. Workflow steps:")
    print("   a. Camera service health check ✓")
    print("   b. Set camera to wardrobe mode ✓")
    print("   c. Start new capture session ✓")

    print("\n4. For each item:")
    print("   a. Select item type (top/bottom/dress/etc)")
    print("   b. Enter item details (name, brand, color)")
    print("   c. Add tags (casual, summer, cotton, etc)")
    print("   d. Position item with guidance")
    print("   e. Countdown (3, 2, 1)")
    print("   f. Capture photo")
    print("   g. Save with metadata")

    print("\n5. Session management:")
    print("   - View captured items summary")
    print("   - Continue or end session")
    print("   - All data saved to organized folders")

    print("\n6. Output structure:")
    print("   photos/wardrobe/{session_id}/")
    print("   ├── top_20250117_143025.jpg")
    print("   ├── top_20250117_143025_metadata.json")
    print("   ├── bottom_20250117_143045.jpg")
    print("   ├── bottom_20250117_143045_metadata.json")
    print("   └── session_summary.json")


def main():
    """Main entry point for manual testing."""
    # Set environment for testing
    os.environ["CAMERA_MODE"] = "hardware_simulation"

    print("Manual Capture Workflow Test")
    print("=" * 50)

    print("\n" + "=" * 50)
    print("To test the interactive CLI workflow:")
    print("1. Start camera service: python camera/camera_service.py")
    print("2. Use camera service API endpoints for manual capture")
    print("=" * 50)


if __name__ == "__main__":
    main()
