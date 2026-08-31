"""Tests for _attach_primary_color（画像アップロード時に色を付ける経路）."""

import io
from typing import Any, Optional

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from app.routers.wardrobe import _attach_primary_color

pytestmark = pytest.mark.asyncio


class _FakeItem:
    """ClothingItem の代わり. この経路が触るのは id と colors_palette だけ."""

    def __init__(self, colors_palette: Optional[dict] = None) -> None:
        self.id = "item-1"
        self.colors_palette: Any = colors_palette


def _upload(color: tuple, filename: str) -> UploadFile:
    """白背景の真ん中に単色を置いた物撮り風の画像を UploadFile にする."""
    image = Image.new("RGB", (160, 160), (255, 255, 255))
    for x in range(40, 120):
        for y in range(40, 120):
            image.putpixel((x, y), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return UploadFile(file=buffer, filename=filename)


def _hex_to_rgb(value: str) -> tuple:
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))


def _distance(value: str, expected: tuple) -> float:
    return sum((a - b) ** 2 for a, b in zip(_hex_to_rgb(value), expected)) ** 0.5


async def test_primary_に採られた写真から色を取る():
    """1 枚目のアップロードが失敗して 2 枚目が primary になっても、色は 2 枚目から取る.

    upload_multiple_images は失敗したファイルを黙って飛ばすため、files の並びと
    uploaded_images の並びは一致しない。添字で対応づけると代表写真と色が食い違う。
    """
    item = _FakeItem()
    files = [_upload((200, 30, 30), "failed.png"), _upload((30, 60, 200), "ok.png")]

    await _attach_primary_color(item, files, {"filename": "ok.png"})

    assert item.colors_palette is not None
    assert _distance(item.colors_palette["palette"][0]["hex"], (30, 60, 200)) < 30


async def test_同名のファイルが複数あるときは色を付けない():
    """どれが primary か決まらないので、間違った色を入れるより付けない方を選ぶ."""
    item = _FakeItem()
    files = [_upload((200, 30, 30), "same.png"), _upload((30, 60, 200), "same.png")]

    await _attach_primary_color(item, files, {"filename": "same.png"})

    assert item.colors_palette is None


async def test_primary_に対応するファイルが無ければ触らない():
    item = _FakeItem()
    files = [_upload((200, 30, 30), "a.png")]

    await _attach_primary_color(item, files, {"filename": "b.png"})

    assert item.colors_palette is None


@pytest.mark.parametrize("method", ["eyedropper", "manual"])
async def test_手で決めた色は上書きしない(method):
    manual = {
        "palette": [{"hex": "#123456", "position": 1}],
        "extraction_method": method,
    }
    item = _FakeItem(manual)
    files = [_upload((30, 60, 200), "a.png")]

    await _attach_primary_color(item, files, {"filename": "a.png"})

    assert item.colors_palette == manual


async def test_抽出に失敗してもアップロードは止めない():
    """色は付加情報なので、壊れた画像でも例外を投げずに素通りする."""
    item = _FakeItem()
    broken = UploadFile(file=io.BytesIO(b"not an image"), filename="broken.png")

    await _attach_primary_color(item, [broken], {"filename": "broken.png"})

    assert item.colors_palette is None
