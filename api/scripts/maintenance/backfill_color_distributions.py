#!/usr/bin/env python3
"""Backfill color distributions for existing wardrobe items."""

import os
import sys

import requests

# Add the API path to find the modules
sys.path.insert(0, os.path.dirname(__file__))

REQUEST_TIMEOUT = 30
# 画像アップロードは色分析を同期で走らせるので長めに取る
UPLOAD_TIMEOUT = 120


def backfill_color_distributions() -> None:
    """Re-upload images for existing wardrobe items to trigger color analysis."""
    try:
        # Get all wardrobe items
        response = requests.get(
            "http://localhost:8000/api/v2/wardrobe/items", timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            print(f"❌ Failed to get wardrobe items: {response.status_code}")
            return

        items = response.json()
        print(f"📦 Found {len(items)} wardrobe items")

        updated_count = 0

        for item in items:
            item_id = item["id"]
            name = item["name"]
            image_urls = item.get("image_urls", [])
            has_color_data = (
                item.get("image_metadata", {}).get("color_distribution") is not None
            )

            print(f"\n🔍 Processing {name} ({item_id})")
            print(f"   Images: {len(image_urls)}")
            print(f"   Has color data: {has_color_data}")

            if has_color_data:
                print("   ✅ Already has color distribution data")
                continue

            if not image_urls:
                print("   ⚠️ No images available")
                continue

            # Download and re-upload the first image to trigger color analysis
            first_image_url = image_urls[0]

            # Convert relative URL to full path
            if first_image_url.startswith("/static/wardrobe/"):
                image_path = first_image_url.replace(
                    "/static/wardrobe/", "./wardrobe_images/"
                )

                if os.path.exists(image_path):
                    print(f"   🔄 Re-uploading image: {image_path}")

                    # Read the image file
                    with open(image_path, "rb") as f:
                        files = {
                            "files": (os.path.basename(image_path), f, "image/jpeg")
                        }

                        # Re-upload to trigger color analysis
                        upload_response = requests.post(
                            f"http://localhost:8000/api/v2/wardrobe/items/{item_id}/images",
                            files=files,
                            timeout=UPLOAD_TIMEOUT,
                        )

                        if upload_response.status_code == 200:
                            print("   ✅ Successfully updated with color analysis")
                            updated_count += 1
                        else:
                            print(f"   ❌ Upload failed: {upload_response.status_code}")
                            print(f"      Response: {upload_response.text[:200]}")
                else:
                    print(f"   ❌ Image file not found: {image_path}")
            else:
                print(f"   ⚠️ Unsupported image URL format: {first_image_url}")

        print(
            f"\n🎉 Backfill completed! Updated {updated_count} items with color analysis."
        )

    except Exception as e:
        print(f"❌ Error during backfill: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("🎨 Starting color distribution backfill for wardrobe items...")
    backfill_color_distributions()
