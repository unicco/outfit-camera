#!/usr/bin/env python3
"""Match daily outfit photos with pre-registered wardrobe items.

This approach uses pre-photographed flat-lay images as the wardrobe database
and matches them against daily full-body photos.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

sys.path.append(str(Path(__file__).parent.parent))

from coordinate_recorder.logging_config import configure_logging

configure_logging()


class WardrobeMatcher:
    """Match detected clothing items with pre-registered wardrobe."""

    def __init__(self, wardrobe_dir: Path):
        """Initialize with wardrobe directory containing flat-lay photos.

        Expected structure:
        wardrobe/
        ├── tops/
        │   ├── white_tshirt/
        │   │   ├── front.jpg
        │   │   └── metadata.json
        │   └── blue_shirt/
        │       ├── front.jpg
        │       └── metadata.json
        └── bottoms/
            └── black_skirt/
                ├── front.jpg
                └── metadata.json
        """
        self.wardrobe_dir = wardrobe_dir
        self.wardrobe_items = self._load_wardrobe()

    def _load_wardrobe(self) -> dict[str, dict]:
        """Load all wardrobe items with their features."""
        items = {}

        for category_dir in self.wardrobe_dir.iterdir():
            if not category_dir.is_dir():
                continue

            for item_dir in category_dir.iterdir():
                if not item_dir.is_dir():
                    continue

                # Load item data
                img_path = item_dir / "front.jpg"
                meta_path = item_dir / "metadata.json"

                if img_path.exists():
                    # Extract features
                    img = cv2.imread(str(img_path))
                    features = self._extract_features(img)

                    # Load metadata
                    metadata = {}
                    if meta_path.exists():
                        with open(meta_path) as f:
                            metadata = json.load(f)

                    item_id = f"{category_dir.name}/{item_dir.name}"
                    items[item_id] = {
                        "path": img_path,
                        "features": features,
                        "metadata": metadata,
                        "category": category_dir.name,
                    }

        print(f"Loaded {len(items)} wardrobe items")
        return items

    def _extract_features(self, image: np.ndarray) -> np.ndarray:
        """Extract features from image for matching.

        Simple approach using:
        - Color histogram
        - Average color
        - Basic shape features
        """
        # Resize to standard size
        standard_size = (128, 128)
        resized = cv2.resize(image, standard_size)

        # Color histogram (HSV)
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)

        # Histogram for each channel
        hist_h = cv2.calcHist([hsv], [0], None, [50], [0, 180])
        hist_s = cv2.calcHist([hsv], [1], None, [60], [0, 256])
        hist_v = cv2.calcHist([hsv], [2], None, [60], [0, 256])

        # Normalize histograms
        hist_h = hist_h.flatten() / hist_h.sum()
        hist_s = hist_s.flatten() / hist_s.sum()
        hist_v = hist_v.flatten() / hist_v.sum()

        # Combine features
        features = np.concatenate([hist_h, hist_s, hist_v])

        return features

    def match_item(
        self,
        detected_image: np.ndarray,
        category: str | None = None,
        threshold: float = 0.7,
    ) -> list[tuple[str, float]]:
        """Match a detected clothing item with wardrobe items.

        Args:
            detected_image: Cropped image of detected item
            category: Optional category filter (tops, bottoms, etc.)
            threshold: Minimum similarity score

        Returns:
            List of (item_id, similarity_score) sorted by score

        """
        # Extract features from detected item
        detected_features = self._extract_features(detected_image)

        # Compare with wardrobe items
        matches = []

        for item_id, item_data in self.wardrobe_items.items():
            # Filter by category if specified
            if category and item_data["category"] != category:
                continue

            # Calculate similarity
            similarity = cosine_similarity(
                detected_features.reshape(1, -1), item_data["features"].reshape(1, -1)
            )[0, 0]

            if similarity >= threshold:
                matches.append((item_id, float(similarity)))

        # Sort by similarity
        matches.sort(key=lambda x: x[1], reverse=True)

        return matches

    def create_outfit_record(
        self,
        photo_path: Path,
        detected_items: list[dict],
        matched_items: dict[int, str],
    ) -> dict:
        """Create outfit record with matched wardrobe items.

        Args:
            photo_path: Path to full-body photo
            detected_items: List of detected regions
            matched_items: Mapping of detection index to wardrobe item ID

        Returns:
            Outfit record dictionary

        """
        outfit = {
            "date": photo_path.stem,  # Assuming filename is date
            "photo": photo_path.name,
            "items": [],
        }

        for idx, detection in enumerate(detected_items):
            if idx in matched_items:
                # Matched with wardrobe item
                item_id = matched_items[idx]
                item_data = self.wardrobe_items[item_id]

                outfit["items"].append(
                    {
                        "wardrobe_id": item_id,
                        "category": item_data["category"],
                        "name": item_data["metadata"].get("name", item_id),
                        "confidence": detection.get("confidence", 1.0),
                        "matched": True,
                    }
                )
            else:
                # Unknown item
                outfit["items"].append(
                    {
                        "wardrobe_id": None,
                        "category": detection.get("category", "unknown"),
                        "name": "Unknown item",
                        "confidence": detection.get("confidence", 0.0),
                        "matched": False,
                        "detection": detection,
                    }
                )

        return outfit


def interactive_matching(
    photo_path: Path, wardrobe_matcher: WardrobeMatcher, output_dir: Path
):
    """Interactive matching process with manual selection for unknown items."""
    print(f"\nProcessing: {photo_path.name}")

    # Read image
    img = cv2.imread(str(photo_path))
    if img is None:
        return

    # For now, use simple region extraction
    # In production, use proper clothing detection
    height, width = img.shape[:2]

    # Simple regions (will be replaced with actual detection)
    regions = [
        {"name": "top", "bbox": (0, 0, width, int(height * 0.5))},
        {"name": "bottom", "bbox": (0, int(height * 0.5), width, int(height * 0.5))},
    ]

    matched_items = {}

    for idx, region in enumerate(regions):
        x, y, w, h = region["bbox"]
        cropped = img[y : y + h, x : x + w]

        # Find matches
        matches = wardrobe_matcher.match_item(
            cropped,
            category=region["name"] + "s",  # tops, bottoms
        )

        if matches:
            # Show top match
            best_match, score = matches[0]
            print(f"\n{region['name'].upper()}:")
            print(f"  Best match: {best_match} (score: {score:.2f})")

            if score >= 0.8:
                # High confidence - auto accept
                matched_items[idx] = best_match
                print("  ✓ Auto-matched")
            else:
                # Low confidence - ask user
                print("  ? Low confidence. Options:")
                print(f"  1. Accept match: {best_match}")
                print("  2. Mark as unknown")
                print("  3. Select different item")

                # For demo, auto-accept
                matched_items[idx] = best_match
        else:
            print(f"\n{region['name'].upper()}: No matches found")

    # Create outfit record
    outfit = wardrobe_matcher.create_outfit_record(photo_path, regions, matched_items)

    # Save result
    output_path = output_dir / f"{photo_path.stem}_outfit.json"
    with open(output_path, "w") as f:
        json.dump(outfit, f, indent=2, ensure_ascii=False)

    print(f"\nOutfit saved to: {output_path}")
    return outfit


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Match daily photos with wardrobe items"
    )
    parser.add_argument(
        "wardrobe_dir", type=Path, help="Directory containing wardrobe flat-lay photos"
    )
    parser.add_argument("photo", type=Path, help="Daily photo to process")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("annotations/outfit_records"),
        help="Output directory for outfit records",
    )

    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize matcher
    matcher = WardrobeMatcher(args.wardrobe_dir)

    # Process photo
    interactive_matching(args.photo, matcher, args.output_dir)


if __name__ == "__main__":
    main()
