"""物撮り写真から衣類の主要色を抽出する.

アイテムマスタの写真は白背景の物撮りで、肌が入らない。1 着につき 1 回だけ
決めればよいので、日ごとの推定を持たない。

背景の落とし方は 2 段構え:
- alpha チャンネルがあればそれを前景マスクに使う
- 無ければ四隅から背景色を推定し、そこから離れたピクセルだけを残す

本番 111 件のうち JPG が 92 件で alpha を持たないため、四隅推定が主経路になる。
"""

import io
import logging
import re
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

logger = logging.getLogger(__name__)

MAX_DIMENSION = 300
# デコード後の画素数の上限。アップロード側のバイト上限（25MB）は画素数を縛れず、
# 小さく圧縮した巨大画像で imdecode がメモリを食い尽くせる。物撮りは大きくても
# 4000x4000 程度なので 5000 万画素あれば足りる
MAX_PIXELS = 50_000_000
# 背景色とみなす RGB 距離。物撮りの白背景と服の境目が分かれる値を実測で選んだ
BACKGROUND_DISTANCE = 40.0
# 前景がこの割合を下回ったら背景除去を諦める。背景と同系色の服を丸ごと落とさないため
MIN_FOREGROUND_RATIO = 0.03
# alpha を前景マスクとして信じる下限。全面不透明の PNG は alpha が無いのと同じ
MIN_TRANSPARENT_RATIO = 0.02
# 背景が抜かれた画像は四隅がまるごと透明になる。実測では該当する 2 件とも 100%
MIN_CORNER_TRANSPARENT_RATIO = 0.9
DEFAULT_NUM_COLORS = 5

_HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")

METHOD_AUTO = "auto_kmeans"
METHOD_EYEDROPPER = "eyedropper"
# ClothingItem.color_primary の setter が書く方の手動表記。eyedropper と併存している
METHOD_MANUAL = "manual"
MANUAL_METHODS = frozenset({METHOD_EYEDROPPER, METHOD_MANUAL})


class ItemColorExtractionError(Exception):
    """色抽出に失敗した."""


def _guard_pixels(image_data: bytes) -> None:
    """デコードの前にヘッダだけ読んで画素数を見る.

    PIL の open はヘッダで止まるので、ここで弾けば imdecode に巨大な画像を渡さずに済む。

    Raises:
        ItemColorExtractionError: 画素数が上限を超える、またはヘッダを読めない場合

    """
    try:
        with Image.open(io.BytesIO(image_data)) as probe:
            width, height = probe.size
    except Exception as e:
        raise ItemColorExtractionError(f"画像のヘッダを読めない: {e}") from e

    if width * height > MAX_PIXELS:
        raise ItemColorExtractionError(f"画素数が多すぎる: {width}x{height}")


def _decode(image_data: bytes) -> tuple[np.ndarray, Optional[np.ndarray]]:
    """バイト列を RGB 画像と alpha チャンネルに分解し、縮小して返す."""
    _guard_pixels(image_data)
    array = np.frombuffer(image_data, np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ItemColorExtractionError("画像をデコードできない")

    alpha = None
    if image.ndim == 3 and image.shape[2] == 4:
        alpha = image[:, :, 3]
        image = image[:, :, :3]
    elif image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

    # IMREAD_UNCHANGED は 16bit PNG を 0-65535 のまま返す。_to_hex は 0-255 前提で、
    # そのままだと "#1F401F401F40" のような 12 桁が colors_palette に入る
    if image.dtype == np.uint16:
        image = (image / 257).astype(np.uint8)
        if alpha is not None:
            alpha = (alpha / 257).astype(np.uint8)
    elif image.dtype != np.uint8:
        raise ItemColorExtractionError(f"扱えない画素形式: {image.dtype}")

    height, width = image.shape[:2]
    scale = MAX_DIMENSION / max(height, width)
    if scale < 1:
        size = (int(width * scale), int(height * scale))
        image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
        if alpha is not None:
            alpha = cv2.resize(alpha, size, interpolation=cv2.INTER_AREA)

    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB), alpha


def _estimate_background(rgb: np.ndarray) -> np.ndarray:
    """四隅 5% 四方の中央値を背景色とみなす."""
    height, width = rgb.shape[:2]
    corner_h, corner_w = max(1, height // 20), max(1, width // 20)
    corners = [
        rgb[:corner_h, :corner_w],
        rgb[:corner_h, -corner_w:],
        rgb[-corner_h:, :corner_w],
        rgb[-corner_h:, -corner_w:],
    ]
    flat = np.concatenate([c.reshape(-1, 3) for c in corners])
    return np.median(flat, axis=0)


def _is_background_mask(alpha: np.ndarray) -> bool:
    """alpha が「背景を抜いた跡」かどうか.

    透明ピクセルがあるだけでは足りない。白背景のまま一部だけ透明な PNG を
    マスクとして使うと、白背景が前景に残って主要色が白になる。四隅まで
    抜けているものだけをマスクとして信じる。
    """
    if float((alpha < 128).mean()) <= MIN_TRANSPARENT_RATIO:
        return False

    height, width = alpha.shape
    corner_h, corner_w = max(1, height // 20), max(1, width // 20)
    corners = np.concatenate(
        [
            alpha[:corner_h, :corner_w].ravel(),
            alpha[:corner_h, -corner_w:].ravel(),
            alpha[-corner_h:, :corner_w].ravel(),
            alpha[-corner_h:, -corner_w:].ravel(),
        ]
    )
    return float((corners < 128).mean()) > MIN_CORNER_TRANSPARENT_RATIO


def _foreground_pixels(
    rgb: np.ndarray, alpha: Optional[np.ndarray]
) -> tuple[np.ndarray, str]:
    """背景を落として前景ピクセルだけを返す. 落とし方の名前も返す."""
    pixels = rgb.reshape(-1, 3).astype(np.float32)

    if alpha is not None and _is_background_mask(alpha):
        return pixels[alpha.ravel() > 128], "alpha"

    background = _estimate_background(rgb).astype(np.float32)
    distance = np.linalg.norm(pixels - background, axis=1)
    foreground = pixels[distance > BACKGROUND_DISTANCE]
    if len(foreground) < len(pixels) * MIN_FOREGROUND_RATIO:
        # 服が背景と同系色。除去せず全体を使う（白い服が丸ごと消えるのを避ける）
        return pixels, "whole"
    return foreground, "corner"


def _to_hex(rgb: np.ndarray) -> str:
    return "#%02X%02X%02X" % tuple(int(round(float(v))) for v in rgb)


def extract_palette(
    image_data: bytes, num_colors: int = DEFAULT_NUM_COLORS
) -> Dict[str, Any]:
    """物撮り写真から主要色のパレットを作る.

    Args:
        image_data: 画像のバイト列
        num_colors: K-means のクラスタ数

    Returns:
        colors_palette 列にそのまま入る辞書。占有率の高い順に並ぶ

    Raises:
        ItemColorExtractionError: デコードできない、または前景が空だった場合

    """
    rgb, alpha = _decode(image_data)
    foreground, mask_method = _foreground_pixels(rgb, alpha)
    if len(foreground) == 0:
        raise ItemColorExtractionError("前景ピクセルが無い")

    clusters = min(num_colors, len(foreground))
    kmeans = KMeans(n_clusters=clusters, random_state=42, n_init=10)
    kmeans.fit(foreground)

    _, counts = np.unique(kmeans.labels_, return_counts=True)
    order = np.argsort(-counts)

    palette: List[Dict[str, Any]] = []
    for position, index in enumerate(order, start=1):
        palette.append(
            {
                "hex": _to_hex(kmeans.cluster_centers_[index]),
                "position": position,
                "ratio": round(float(counts[index]) / len(foreground), 4),
            }
        )

    return {
        "palette": palette,
        "extraction_method": METHOD_AUTO,
        "mask_method": mask_method,
    }


def is_valid_hex(value: str) -> bool:
    """#RRGGBB の形かどうか. 色を保存する経路はすべてここを通す."""
    return bool(_HEX_PATTERN.match(value))


def is_manually_set(colors_palette: Optional[Dict[str, Any]]) -> bool:
    """人が手で決めた色かどうか. 自動抽出で上書きしてよいかの判定に使う."""
    if not isinstance(colors_palette, dict):
        return False
    return colors_palette.get("extraction_method") in MANUAL_METHODS
