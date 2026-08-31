#!/usr/bin/env python3
"""Create outfit record via API endpoint."""

from datetime import datetime
from typing import Optional

import requests

REQUEST_TIMEOUT = 30


def create_wardrobe_item(
    name: str, category: str = "tops", color: str = "blue"
) -> Optional[str]:
    """Create a wardrobe item and return its ID."""
    item_data = {
        "name": f"{color} {category}",
        "category": category,
        "color_primary": color,
        "brand": "Test Brand",
        "size": "M",
        "purchase_date": datetime.now().strftime("%Y-%m-%d"),
    }

    try:
        response = requests.post(
            "http://localhost:8000/wardrobe/items",
            json=item_data,
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code in [200, 201]:
            item = response.json()
            print(f"Created wardrobe item: {item['name']} with ID: {item['id']}")
            return str(item["id"])
        else:
            print(f"Failed to create wardrobe item: {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except Exception as e:
        print(f"Error creating wardrobe item: {e}")
        return None


def create_outfit_record(photo_id: str, clothing_item_id: str) -> None:
    """Create outfit record via API."""
    # Data for outfit record
    outfit_data = {
        "photo_id": photo_id,
        "clothing_item_ids": [clothing_item_id],
        "notes": "Manually added for UI testing",
    }

    try:
        # Post to outfit record endpoint
        response = requests.post(
            "http://localhost:8000/api/v2/outfits/record",
            json=outfit_data,
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 200:
            print(f"Successfully created outfit record for {photo_id}")
            print(f"Response: {response.json()}")
        else:
            print(f"Failed to create outfit record: {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"Error creating outfit record: {e}")


if __name__ == "__main__":
    photo_id = "0aa30bbe-db92-4063-a4cd-dab9f12d3698"

    # First create a wardrobe item
    clothing_item_id = create_wardrobe_item("Test Top", "tops", "blue")

    if clothing_item_id:
        # Then create outfit record
        create_outfit_record(photo_id, clothing_item_id)
