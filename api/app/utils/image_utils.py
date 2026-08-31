"""画像処理ユーティリティ.

画像の読み込み、リサイズ、フォーマット変換などの共通処理を提供
"""

import io
import logging
from typing import Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def load_image_from_bytes(
    image_bytes: bytes, mode: str = "cv2"
) -> Optional[Union[np.ndarray, Image.Image]]:
    """バイト列から画像を読み込む.

    Args:
        image_bytes: 画像のバイト列
        mode: "cv2" (OpenCV形式) または "pil" (PIL形式)

    Returns:
        画像オブジェクト (失敗時はNone)

    """
    try:
        if mode == "cv2":
            # OpenCV形式 (BGR)
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image is None:
                logger.error("Failed to decode image with OpenCV")
                return None
            return image
        elif mode == "pil":
            # PIL形式 (RGB)
            pil_image: Image.Image = Image.open(io.BytesIO(image_bytes))
            return pil_image
        else:
            logger.error(f"Unknown mode: {mode}")
            return None
    except Exception as e:
        logger.error(f"Failed to load image from bytes: {e}")
        return None


def convert_pil_to_cv2(pil_image: Image.Image) -> np.ndarray:
    """PIL画像をOpenCV形式に変換.

    Args:
        pil_image: PIL画像

    Returns:
        OpenCV形式の画像 (BGR)

    """
    # RGBAの場合はRGBに変換
    if pil_image.mode == "RGBA":
        # 白背景でアルファチャンネルを合成
        background = Image.new("RGB", pil_image.size, (255, 255, 255))
        background.paste(pil_image, mask=pil_image.split()[3])
        pil_image = background
    elif pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")

    # numpy配列に変換してBGRに
    rgb_array = np.array(pil_image)
    bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
    return bgr_array


def convert_cv2_to_pil(cv2_image: np.ndarray) -> Image.Image:
    """OpenCV画像をPIL形式に変換.

    Args:
        cv2_image: OpenCV形式の画像 (BGR)

    Returns:
        PIL画像 (RGB)

    """
    rgb_array = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb_array)


def resize_image_with_aspect_ratio(
    image: Union[np.ndarray, Image.Image],
    max_size: int,
    interpolation: Optional[int] = None,
) -> Union[np.ndarray, Image.Image]:
    """アスペクト比を保持してリサイズ.

    Args:
        image: 画像 (OpenCV または PIL)
        max_size: 最大寸法（幅または高さの大きい方）
        interpolation: 補間方法

    Returns:
        リサイズされた画像

    """
    if isinstance(image, np.ndarray):
        # OpenCV形式
        height, width = image.shape[:2]
        if interpolation is None:
            interpolation = (
                cv2.INTER_AREA if max(width, height) > max_size else cv2.INTER_LINEAR
            )

        # アスペクト比を計算
        if width > height:
            new_width = max_size
            new_height = int(height * max_size / width)
        else:
            new_height = max_size
            new_width = int(width * max_size / height)

        return cv2.resize(image, (new_width, new_height), interpolation=interpolation)

    elif isinstance(image, Image.Image):
        # PIL形式
        width, height = image.size

        # アスペクト比を計算
        if width > height:
            new_width = max_size
            new_height = int(height * max_size / width)
        else:
            new_height = max_size
            new_width = int(width * max_size / height)

        resampling = (
            Image.Resampling.LANCZOS if interpolation is None else interpolation
        )
        return image.resize((new_width, new_height), resampling)

    else:
        raise ValueError(f"Unsupported image type: {type(image)}")


def resize_image_to_square(
    image: Union[np.ndarray, Image.Image], size: int, crop: bool = True
) -> Union[np.ndarray, Image.Image]:
    """正方形にリサイズ.

    Args:
        image: 画像
        size: 出力サイズ
        crop: True=中央をクロップ、False=パディング

    Returns:
        正方形の画像

    """
    if isinstance(image, np.ndarray):
        # OpenCV形式
        height, width = image.shape[:2]

        if crop:
            # 中央をクロップ
            min_dim = min(width, height)
            x_offset = (width - min_dim) // 2
            y_offset = (height - min_dim) // 2
            cropped = image[
                y_offset : y_offset + min_dim, x_offset : x_offset + min_dim
            ]
            return cv2.resize(cropped, (size, size), interpolation=cv2.INTER_AREA)
        else:
            # パディング
            resized_img = resize_image_with_aspect_ratio(image, size)
            # 型チェック用のキャスト
            if not isinstance(resized_img, np.ndarray):
                raise ValueError("Expected numpy array from resize operation")
            h, w = resized_img.shape[:2]

            # パディングを追加
            top = (size - h) // 2
            bottom = size - h - top
            left = (size - w) // 2
            right = size - w - left

            return cv2.copyMakeBorder(
                resized_img,
                top,
                bottom,
                left,
                right,
                cv2.BORDER_CONSTANT,
                value=(255, 255, 255),
            )

    elif isinstance(image, Image.Image):
        # PIL形式
        width, height = image.size

        if crop:
            # 中央をクロップ
            min_dim = min(width, height)
            left = (width - min_dim) // 2
            top = (height - min_dim) // 2
            right = left + min_dim
            bottom = top + min_dim
            cropped_pil: Image.Image = image.crop((left, top, right, bottom))
            return cropped_pil.resize((size, size), Image.Resampling.LANCZOS)
        else:
            # パディング
            resized_img = resize_image_with_aspect_ratio(image, size)

            # 型チェック用のキャスト
            if not isinstance(resized_img, Image.Image):
                raise ValueError("Expected PIL Image from resize operation")

            # 新しい白背景画像を作成
            new_image = Image.new("RGB", (size, size), (255, 255, 255))

            # 中央に配置
            x = (size - resized_img.width) // 2
            y = (size - resized_img.height) // 2
            new_image.paste(resized_img, (x, y))

            return new_image

    else:
        raise ValueError(f"Unsupported image type: {type(image)}")


def ensure_rgb_format(image: Image.Image) -> Image.Image:
    """画像をRGB形式に変換（JPEG保存用）.

    Args:
        image: PIL画像

    Returns:
        RGB形式の画像

    """
    if image.mode == "RGBA":
        # 白背景でアルファチャンネルを合成
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        return background
    elif image.mode != "RGB":
        return image.convert("RGB")
    return image


def save_image_to_bytes(
    image: Union[np.ndarray, Image.Image], format: str = "JPEG", quality: int = 85
) -> bytes:
    """画像をバイト列に変換.

    Args:
        image: 画像
        format: 画像フォーマット (JPEG, PNG など)
        quality: JPEG品質 (1-100)

    Returns:
        画像のバイト列

    """
    buffer = io.BytesIO()

    if isinstance(image, np.ndarray):
        # OpenCVからPILに変換
        image = convert_cv2_to_pil(image)

    if format.upper() == "JPEG":
        # JPEG保存時はRGB形式に変換
        image = ensure_rgb_format(image)

    image.save(buffer, format=format, quality=quality)
    return buffer.getvalue()


def get_image_dimensions(image: Union[np.ndarray, Image.Image]) -> Tuple[int, int]:
    """画像の寸法を取得.

    Args:
        image: 画像

    Returns:
        (width, height)

    """
    if isinstance(image, np.ndarray):
        height, width = image.shape[:2]
        return width, height
    elif isinstance(image, Image.Image):
        return image.size
    else:
        raise ValueError(f"Unsupported image type: {type(image)}")
