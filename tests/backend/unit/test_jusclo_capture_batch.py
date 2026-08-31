from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from coordinate_recorder.jusclo_capture_batch import (
    JuscloGridConfig,
    extract_non_empty_tiles,
    process_jusclo_directory,
    save_horizontal_strips_for_file,
)


def _draw_slot(
    image: Image.Image,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    fill: tuple[int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    draw.rectangle((x, y, x + width, y + height), fill=(250, 250, 250))
    for idx in range(0, width, 6):
        draw.line((x + idx, y, x + width - idx // 2, y + height), fill=fill, width=2)


def _build_test_image(config: JuscloGridConfig) -> Image.Image:
    image = Image.new("RGB", (config.base_width, config.base_height), (236, 236, 236))
    # 4x4 のうち 3 枠のみを非空として描画
    _draw_slot(
        image,
        x=config.x_positions[0],
        y=config.y_positions[0],
        width=config.item_width,
        height=config.item_height,
        fill=(20, 140, 220),
    )
    _draw_slot(
        image,
        x=config.x_positions[2],
        y=config.y_positions[1],
        width=config.item_width,
        height=config.item_height,
        fill=(200, 80, 40),
    )
    _draw_slot(
        image,
        x=config.x_positions[1],
        y=config.y_positions[3],
        width=config.item_width,
        height=config.item_height,
        fill=(30, 30, 30),
    )
    return image


@pytest.mark.unit
def test_extract_non_empty_tiles_filters_empty_slots() -> None:
    config = JuscloGridConfig()
    image = _build_test_image(config)

    tiles = extract_non_empty_tiles(image, config=config)

    assert len(tiles) == 3
    first_meta = tiles[0][0]
    assert first_meta.row_index == 0
    assert first_meta.col_index == 0


@pytest.mark.unit
def test_extract_non_empty_tiles_scales_with_resolution() -> None:
    config = JuscloGridConfig()
    image = _build_test_image(config).resize((540, 1205))

    tiles = extract_non_empty_tiles(image, config=config)

    assert len(tiles) == 3
    first_bbox = tiles[0][0].bbox
    assert first_bbox[0] == 11
    assert first_bbox[1] == 108


@pytest.mark.unit
def test_process_jusclo_directory_creates_tiles_and_month_strip(tmp_path: Path) -> None:
    config = JuscloGridConfig()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "tiles"
    month_strip = tmp_path / "month" / "2025-09.png"
    input_dir.mkdir(parents=True)

    _build_test_image(config).save(input_dir / "sample_a.png")
    _build_test_image(config).save(input_dir / "sample_b.png")

    result = process_jusclo_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        month_output_path=month_strip,
        config=config,
    )

    assert result == {"input_images": 2, "output_tiles": 6}
    assert len(list(output_dir.glob("*.png"))) == 6
    assert month_strip.exists()


@pytest.mark.unit
def test_save_horizontal_strips_for_file(tmp_path: Path) -> None:
    image = Image.new("RGB", (1080, 2410), (120, 130, 140))
    input_file = tmp_path / "202509-top.png"
    out_dir = tmp_path / "strips"
    image.save(input_file)

    saved = save_horizontal_strips_for_file(
        image_path=input_file,
        output_dir=out_dir,
        y_points=[474, 978, 1482],
        strip_width=1080,
        strip_height=209,
    )

    assert len(saved) == 3
    for path in saved:
        strip = Image.open(path)
        assert strip.size == (1080, 209)
