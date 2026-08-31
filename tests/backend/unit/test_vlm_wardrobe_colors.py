"""Tests for ClothingDetectorV2._update_wardrobe_colors（VLM の色反映）."""

from typing import Any, Optional
from unittest.mock import MagicMock

from app.routers.ai_detection import ClothingDetectorV2


class _FakeItem:
    """ClothingItem の代わり. この経路が触るのは colors_palette だけ."""

    def __init__(self, colors_palette: Optional[dict] = None) -> None:
        self.colors_palette: Any = colors_palette


def _apply(item: _FakeItem, color_hex: str = "#AABBCC") -> None:
    matches = [{"color_hex": color_hex, "wardrobe_item_id": "item-1"}]
    ClothingDetectorV2._update_wardrobe_colors(matches, {"item-1": item}, MagicMock())


def test_色が無ければ_palette_形式で入る():
    item = _FakeItem()

    _apply(item)

    assert item.colors_palette == {
        "palette": [{"hex": "#AABBCC", "position": 1}],
        "extraction_method": "vlm_gemini",
    }


def test_物撮りから取った色は上書きしない():
    """VLM は全身写真からの判定なので、1 着ずつ取った色より優先しない."""
    existing = {
        "palette": [{"hex": "#112233", "position": 1}],
        "extraction_method": "auto_kmeans",
    }
    item = _FakeItem(dict(existing))

    _apply(item)

    assert item.colors_palette == existing


def test_手で決めた色は_palette_を持たなくても上書きしない():
    """color_primary の setter は palette 無しの manual レコードを作りうる."""
    manual = {"extraction_method": "manual", "color_primary": "#445566"}
    item = _FakeItem(dict(manual))

    _apply(item)

    assert item.colors_palette == manual


def test_hex_の形が不正なら何もしない():
    item = _FakeItem()

    _apply(item, color_hex="not-a-hex")

    assert item.colors_palette is None
