from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageStat


@dataclass(frozen=True)
class JuscloGridConfig:
    base_width: int = 1080
    base_height: int = 2410
    item_width: int = 102
    item_height: int = 136
    x_positions: tuple[int, ...] = (22, 131, 240, 349)
    y_positions: tuple[int, ...] = (216, 498, 781, 1065)
    stddev_threshold: float = 18.0
    dark_pixel_ratio_threshold: float = 0.03


@dataclass(frozen=True)
class CropMeta:
    row_index: int
    col_index: int
    bbox: tuple[int, int, int, int]


def _scale(value: int, actual: int, base: int) -> int:
    return round(value * actual / base)


def _is_non_empty_tile(
    tile: Image.Image, stddev_threshold: float, dark_pixel_ratio_threshold: float
) -> bool:
    gray = tile.convert("L")
    stat = ImageStat.Stat(gray)
    stddev = float(stat.stddev[0]) if stat.stddev else 0.0

    pixels = gray.getdata()
    dark_pixels = sum(1 for value in pixels if value < 225)
    dark_ratio = dark_pixels / max(1, len(pixels))
    return stddev >= stddev_threshold and dark_ratio >= dark_pixel_ratio_threshold


def extract_non_empty_tiles(
    image: Image.Image, config: JuscloGridConfig | None = None
) -> list[tuple[CropMeta, Image.Image]]:
    cfg = config or JuscloGridConfig()
    scaled_w = _scale(cfg.item_width, image.width, cfg.base_width)
    scaled_h = _scale(cfg.item_height, image.height, cfg.base_height)

    results: list[tuple[CropMeta, Image.Image]] = []
    for row_idx, y_base in enumerate(cfg.y_positions):
        y1 = _scale(y_base, image.height, cfg.base_height)
        y2 = min(image.height, y1 + scaled_h)
        for col_idx, x_base in enumerate(cfg.x_positions):
            x1 = _scale(x_base, image.width, cfg.base_width)
            x2 = min(image.width, x1 + scaled_w)
            tile = image.crop((x1, y1, x2, y2))
            if not _is_non_empty_tile(
                tile,
                stddev_threshold=cfg.stddev_threshold,
                dark_pixel_ratio_threshold=cfg.dark_pixel_ratio_threshold,
            ):
                continue
            meta = CropMeta(row_index=row_idx, col_index=col_idx, bbox=(x1, y1, x2, y2))
            results.append((meta, tile))
    return results


def save_tiles_for_image(
    image_path: Path, output_dir: Path, config: JuscloGridConfig | None = None
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(image_path).convert("RGB")
    tiles = extract_non_empty_tiles(image=image, config=config)
    saved_paths: list[Path] = []
    for idx, (meta, tile) in enumerate(tiles, start=1):
        file_name = (
            f"{image_path.stem}_r{meta.row_index + 1:02d}_"
            f"c{meta.col_index + 1:02d}_{idx:03d}.png"
        )
        out_path = output_dir / file_name
        tile.save(out_path)
        saved_paths.append(out_path)
    return saved_paths


def build_month_strip(
    tile_paths: list[Path],
    output_path: Path,
    *,
    tile_width: int = 160,
    tile_height: int = 220,
    margin: int = 18,
    row_height: int = 250,
) -> Path:
    if not tile_paths:
        raise ValueError("tile_paths is empty")

    cols = len(tile_paths)
    width = margin * 2 + cols * tile_width
    height = margin * 2 + row_height
    canvas = Image.new("RGB", (width, height), (248, 248, 248))

    for col, tile_path in enumerate(tile_paths):
        tile = Image.open(tile_path).convert("RGB").resize((tile_width, tile_height))
        x = margin + col * tile_width
        y = margin + (row_height - tile_height) // 2
        canvas.paste(tile, (x, y))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return output_path


def process_jusclo_directory(
    input_dir: Path,
    output_dir: Path,
    month_output_path: Path | None = None,
    config: JuscloGridConfig | None = None,
) -> dict[str, int]:
    images = sorted(input_dir.glob("*.png"))
    all_tiles: list[Path] = []
    for image_path in images:
        all_tiles.extend(
            save_tiles_for_image(
                image_path=image_path, output_dir=output_dir, config=config
            )
        )

    if month_output_path and all_tiles:
        build_month_strip(tile_paths=all_tiles, output_path=month_output_path)

    return {"input_images": len(images), "output_tiles": len(all_tiles)}


def extract_horizontal_strips(
    image: Image.Image, y_points: list[int], *, strip_width: int, strip_height: int
) -> list[tuple[tuple[int, int, int, int], Image.Image]]:
    results: list[tuple[tuple[int, int, int, int], Image.Image]] = []
    width = min(strip_width, image.width)
    for y1 in y_points:
        if y1 < 0:
            continue
        y2 = y1 + strip_height
        if y2 > image.height:
            continue
        bbox = (0, y1, width, y2)
        results.append((bbox, image.crop(bbox)))
    return results


def save_horizontal_strips_for_file(
    image_path: Path,
    output_dir: Path,
    y_points: list[int],
    *,
    strip_width: int = 1080,
    strip_height: int = 209,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    image = Image.open(image_path).convert("RGB")
    strips = extract_horizontal_strips(
        image, y_points=y_points, strip_width=strip_width, strip_height=strip_height
    )
    saved_paths: list[Path] = []
    for idx, (_, strip) in enumerate(strips, start=1):
        out_path = output_dir / f"{image_path.stem}_strip_{idx:02d}.png"
        strip.save(out_path)
        saved_paths.append(out_path)
    return saved_paths
