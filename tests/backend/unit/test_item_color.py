"""Tests for item_color.py（物撮り写真からの主要色抽出）."""

import io
import struct
import zlib

import pytest
from PIL import Image

from app.services import item_color


def _png_header(width: int, height: int) -> bytes:
    """寸法だけを主張する PNG。画素データを持たないので巨大な画像を安全に模せる.

    PIL は IHDR で寸法を確定し、実データは open の時点では読まない。IDAT / IEND は
    ファイルとして識別させるために要る（無いと cannot identify で落ちる）。
    """

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data))
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00"))
        + chunk(b"IEND", b"")
    )


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _on_white(color: tuple, size: int = 200, margin: int = 40) -> Image.Image:
    """白背景の真ん中に単色の四角を置いた、物撮りを模した画像."""
    image = Image.new("RGB", (size, size), (255, 255, 255))
    for x in range(margin, size - margin):
        for y in range(margin, size - margin):
            image.putpixel((x, y), color)
    return image


def _hex_to_rgb(value: str) -> tuple:
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))


def _distance(a: str, b: tuple) -> float:
    return sum((x - y) ** 2 for x, y in zip(_hex_to_rgb(a), b)) ** 0.5


class TestExtractPalette:
    """主要色の抽出."""

    def test_白背景の物撮りから服の色を取る(self):
        palette = item_color.extract_palette(_jpeg(_on_white((30, 60, 140))))

        assert palette["extraction_method"] == item_color.METHOD_AUTO
        assert palette["mask_method"] == "corner"
        # 背景の白ではなく、置いた青が主要色として返る
        assert _distance(palette["palette"][0]["hex"], (30, 60, 140)) < 30

    def test_占有率の高い順に並ぶ(self):
        palette = item_color.extract_palette(_jpeg(_on_white((200, 40, 40))))

        ratios = [c["ratio"] for c in palette["palette"]]
        positions = [c["position"] for c in palette["palette"]]
        assert ratios == sorted(ratios, reverse=True)
        assert positions == list(range(1, len(positions) + 1))

    def test_alpha_があれば前景マスクに使う(self):
        image = Image.new("RGBA", (200, 200), (255, 255, 255, 0))
        for x in range(40, 160):
            for y in range(40, 160):
                image.putpixel((x, y), (20, 150, 90, 255))

        palette = item_color.extract_palette(_png(image))

        assert palette["mask_method"] == "alpha"
        assert _distance(palette["palette"][0]["hex"], (20, 150, 90)) < 30

    def test_一部だけ透明な白背景の_png_は_alpha_をマスクにしない(self):
        """白背景のまま飾りだけ抜けた PNG を alpha マスクにすると、白が主要色になる."""
        image = Image.new("RGBA", (200, 200), (255, 255, 255, 255))
        for x in range(40, 160):
            for y in range(40, 160):
                image.putpixel((x, y), (20, 150, 90, 255))
        # 端に小さな透明穴（全体の 2% 超）を開ける。四隅は不透明のまま
        for x in range(5, 45):
            for y in range(5, 45):
                image.putpixel((x, y), (0, 0, 0, 0))

        palette = item_color.extract_palette(_png(image))

        assert palette["mask_method"] == "corner"
        assert _distance(palette["palette"][0]["hex"], (20, 150, 90)) < 30

    def test_背景と同系色の服は除去を諦めて全体から取る(self):
        # 一面ほぼ白。四隅で背景を推定すると前景が消えてしまうケース
        image = Image.new("RGB", (200, 200), (252, 252, 250))

        palette = item_color.extract_palette(_jpeg(image))

        assert palette["mask_method"] == "whole"
        assert _distance(palette["palette"][0]["hex"], (252, 252, 250)) < 30

    def test_デコードできない入力は例外(self):
        with pytest.raises(item_color.ItemColorExtractionError):
            item_color.extract_palette(b"not an image")

    def test_画素数が多すぎる画像はデコードせずに弾く(self):
        # バイト数の上限（25MB）は画素数を縛れない。ヘッダだけ巨大な PNG を作り、
        # imdecode に渡る前に落ちることを見る（実データを持たないので数十バイト）
        huge = _png_header(8000, 8000)  # 6400 万画素 > MAX_PIXELS

        with pytest.raises(item_color.ItemColorExtractionError, match="画素数"):
            item_color.extract_palette(huge)

    def test_上限内の寸法はヘッダ検査を通る(self):
        palette = item_color.extract_palette(_jpeg(_on_white((10, 120, 60))))

        assert _distance(palette["palette"][0]["hex"], (10, 120, 60)) < 30

    def test_16bit_png_も_6_桁の_hex_になる(self):
        """IMREAD_UNCHANGED は 16bit を 0-65535 のまま返す。落とさないと 12 桁になる."""
        import cv2
        import numpy as np

        array = np.full((160, 160, 3), 65535, dtype=np.uint16)  # 白背景
        array[40:120, 40:120] = (0, 20000, 40000)  # BGR。8bit では約 (0, 78, 156)
        ok, buffer = cv2.imencode(".png", array)
        assert ok

        palette = item_color.extract_palette(buffer.tobytes())

        hex_value = palette["palette"][0]["hex"]
        assert len(hex_value) == 7, hex_value
        # BGR で入れたので RGB では (156, 78, 0) 側に出る
        assert _distance(hex_value, (156, 78, 0)) < 30


class TestIsManuallySet:
    """人が手で決めた色かの判定."""

    @pytest.mark.parametrize("method", ["eyedropper", "manual"])
    def test_手で決めた色は上書きしない(self, method):
        # eyedropper（スポイト UI）と manual（color_primary setter）が併存している
        assert item_color.is_manually_set({"extraction_method": method}) is True

    @pytest.mark.parametrize(
        "value",
        [
            None,
            {},
            {"extraction_method": "vlm_gemini"},
            {"extraction_method": "auto_kmeans"},
        ],
    )
    def test_それ以外は自動で上書きしてよい(self, value):
        assert item_color.is_manually_set(value) is False
