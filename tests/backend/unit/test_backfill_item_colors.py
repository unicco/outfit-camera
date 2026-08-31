"""Tests for backfill_item_colors.should_extract（誰の色を取り直すか）.

本番 DB を書き換える判定なので、飛ばす対象を取り違えると人が決めた色が消える。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "api"
    / "scripts"
    / "maintenance"
    / "backfill_item_colors.py"
)
_spec = importlib.util.spec_from_file_location("backfill_item_colors", _SCRIPT)
assert _spec is not None and _spec.loader is not None
backfill_item_colors = importlib.util.module_from_spec(_spec)
sys.modules["backfill_item_colors"] = backfill_item_colors
_spec.loader.exec_module(backfill_item_colors)

should_extract = backfill_item_colors.should_extract


@pytest.mark.parametrize("method", ["eyedropper", "manual"])
def test_人が決めた色は取り直さない(method):
    palette = {
        "palette": [{"hex": "#123456", "position": 1}],
        "extraction_method": method,
    }

    assert should_extract(palette) is False


def test_物撮りから取った色は取り直さない():
    """再実行しても済んだ分は飛ばす."""
    palette = {
        "palette": [{"hex": "#1A1B1C", "position": 1}],
        "extraction_method": "auto_kmeans",
    }

    assert should_extract(palette) is False


def test_vlm_が_palette_形式で書いた色は取り直す():
    """中身が CSS 定数なので、形が揃っていても取り直す対象."""
    palette = {
        "palette": [{"hex": "#000000", "position": 1}],
        "extraction_method": "vlm_gemini",
    }

    assert should_extract(palette) is True


def test_vlm_の旧形式も取り直す():
    assert should_extract({"vlm_color_hex": "#000000"}) is True


@pytest.mark.parametrize("value", [None, {}, {"extraction_method": "auto_kmeans"}])
def test_色が入っていなければ取り直す(value):
    # 方式だけあって palette が空のものも対象（過去に途中まで書かれた形）
    assert should_extract(value) is True
