#!/usr/bin/env python3
"""Test script for Outfit API endpoints
Issue #200 implementation test.
"""

import asyncio
import os
import sys
import uuid

import pytest

# Add API directory to Python path
api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, api_dir)


def test_outfit_api():
    """Test the outfit API endpoints."""
    pytest.skip("Integration test - requires running API server")


async def manual_test_outfit_api():
    """Manual test for outfit API endpoints (run with API server)."""
    try:
        import httpx

        API_BASE = "http://localhost:8000"

        print("🧪 Testing Outfit API endpoints...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test 1: Health check
            print("\n1. 🔍 Health check...")
            try:
                response = await client.get(f"{API_BASE}/healthz")
                print(f"   Health: {response.status_code} - {response.json()}")
            except Exception as e:
                print(f"   ❌ Health check failed: {e}")
                return

            # Test 2: Get clothing items (prerequisite)
            print("\n2. 👕 Getting clothing items...")
            try:
                response = await client.get(f"{API_BASE}/wardrobe/items")
                if response.status_code == 200:
                    clothing_items = response.json()
                    print(f"   Found {len(clothing_items)} clothing items")
                    if clothing_items:
                        sample_item_id = clothing_items[0]["id"]
                        print(f"   Sample item ID: {sample_item_id}")
                    else:
                        print("   ⚠️ No clothing items found - creating test item...")
                        # Create a test clothing item
                        test_item = {
                            "name": "テスト シャツ",
                            "category": "TOPS",
                            "colors_palette": {
                                "palette": [{"hex": "#FFFFFF", "position": 1}]
                            },
                            "subcategory": "t-shirt",
                            "brand": "Test Brand",
                        }
                        create_response = await client.post(
                            f"{API_BASE}/wardrobe/items", json=test_item
                        )
                        if create_response.status_code == 200:
                            created_item = create_response.json()
                            sample_item_id = created_item["id"]
                            print(f"   ✅ Created test item: {sample_item_id}")
                        else:
                            print(
                                f"   ❌ Failed to create test item: {create_response.status_code}"
                            )
                            return
                else:
                    print(f"   ❌ Failed to get clothing items: {response.status_code}")
                    return
            except Exception as e:
                print(f"   ❌ Error getting clothing items: {e}")
                return

            # Test 3: Create outfit record
            print("\n3. 📝 Creating outfit record...")
            test_photo_id = f"test-photo-{uuid.uuid4()}"
            outfit_data = {
                "photo_id": test_photo_id,
                "clothing_item_ids": [sample_item_id],
                "notes": "Test outfit record from automated test",
            }

            try:
                response = await client.post(
                    f"{API_BASE}/api/v2/outfits/record", json=outfit_data
                )
                print(f"   Create outfit: {response.status_code}")
                if response.status_code == 200:
                    result = response.json()
                    print(f"   ✅ Created outfit record: {result['outfit_record_id']}")
                    print(f"   Photo ID: {result['photo_id']}")
                    print(f"   Clothing items count: {result['clothing_items_count']}")
                else:
                    print(f"   ❌ Response: {response.text}")
                    return
            except Exception as e:
                print(f"   ❌ Error creating outfit record: {e}")
                return

            # Test 4: Get outfit record by photo
            print("\n4. 🔍 Getting outfit record by photo...")
            try:
                response = await client.get(
                    f"{API_BASE}/api/v2/outfits/photo/{test_photo_id}"
                )
                print(f"   Get outfit: {response.status_code}")
                if response.status_code == 200:
                    outfit_record = response.json()
                    if outfit_record:
                        print(f"   ✅ Retrieved outfit record: {outfit_record['id']}")
                        print(f"   Photo ID: {outfit_record['photo_id']}")
                        print(f"   Outfit items: {len(outfit_record['outfit_items'])}")
                        print(
                            f"   Manual selection: {outfit_record['manual_selection']}"
                        )
                        if outfit_record["notes"]:
                            print(f"   Notes: {outfit_record['notes']}")
                    else:
                        print("   ⚠️ No outfit record found for photo")
                else:
                    print(f"   ❌ Response: {response.text}")
            except Exception as e:
                print(f"   ❌ Error getting outfit record: {e}")

        print("\n🎉 Outfit API test completed!")

    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Please install: pip install httpx")
    except Exception as e:
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    print("🧪 Starting Outfit API Test Suite")
    print("Make sure the API server is running on http://localhost:8000")
    print("-" * 50)

    asyncio.run(manual_test_outfit_api())
