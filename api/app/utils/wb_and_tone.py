"""ホワイトバランスと色調整モジュール.

全身写真のホワイトバランス補正と色調整を行い、ワードローブ画像との色味の統一を図る
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image

from .image_utils import convert_pil_to_cv2

logger = logging.getLogger(__name__)


class WhiteBalanceConfig:
    """ホワイトバランス設定."""

    def __init__(
        self,
        roi: Optional[Tuple[float, float, float, float]] = None,
        fallback_lab_threshold: Dict[str, float] = None,
    ):
        # ROI は画像サイズに対する比率で指定 (0.0-1.0)
        self.roi = roi or (0.1, 0.1, 0.3, 0.3)  # デフォルト: 左上10%~30%の領域

        # フォールバック用の Lab 色空間しきい値
        self.fallback_lab_threshold = fallback_lab_threshold or {
            "l_min": 70,
            "l_max": 100,
            "a_max": 6,
            "b_max": 6,
        }


class ToneAdjustmentConfig:
    """色調整設定."""

    def __init__(
        self,
        saturation: float = 0.9,
        contrast: float = 1.05,
        brightness: float = 0.0,
    ):
        self.saturation = saturation  # 彩度 (0.85-0.95推奨)
        self.contrast = contrast  # コントラスト (1.03-1.08推奨)
        self.brightness = brightness  # 明度調整 (-20～+20)


class ImageColorProcessor:
    """画像の色処理クラス."""

    def __init__(self, config_path: Optional[str] = None):
        """初期化.

        Args:
            config_path: 設定ファイルのパス

        """
        self.config_path = config_path
        self._load_config()

    def _load_config(self):
        """設定ファイルを読み込む."""
        if self.config_path and Path(self.config_path).exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                # ホワイトバランス設定
                wb_config = config.get("white_balance", {})
                self.wb_config = WhiteBalanceConfig(
                    roi=wb_config.get("roi"),
                    fallback_lab_threshold=wb_config.get("fallback_lab_threshold"),
                )

                # 色調整設定
                tone_config = config.get("tone_adjustment", {})
                self.tone_config = ToneAdjustmentConfig(
                    saturation=tone_config.get("saturation", 0.9),
                    contrast=tone_config.get("contrast", 1.05),
                    brightness=tone_config.get("brightness", 0.0),
                )

                logger.info(f"設定ファイルを読み込みました: {self.config_path}")
            except Exception as e:
                logger.warning(f"設定ファイルの読み込みに失敗しました: {e}")
                self._set_default_config()
        else:
            self._set_default_config()

    def _set_default_config(self):
        """デフォルト設定を設定."""
        self.wb_config = WhiteBalanceConfig()
        self.tone_config = ToneAdjustmentConfig()

    def save_config(self, config_path: Optional[str] = None):
        """設定をファイルに保存."""
        save_path = config_path or self.config_path
        if not save_path:
            raise ValueError("保存先パスが指定されていません")

        config = {
            "white_balance": {
                "roi": self.wb_config.roi,
                "fallback_lab_threshold": self.wb_config.fallback_lab_threshold,
            },
            "tone_adjustment": {
                "saturation": self.tone_config.saturation,
                "contrast": self.tone_config.contrast,
                "brightness": self.tone_config.brightness,
            },
        }

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info(f"設定を保存しました: {save_path}")

    def _get_roi_coordinates(
        self, image_shape: Tuple[int, int]
    ) -> Tuple[int, int, int, int]:
        """比率から実際の ROI 座標を計算."""
        height, width = image_shape[:2]
        x1 = int(width * self.wb_config.roi[0])
        y1 = int(height * self.wb_config.roi[1])
        x2 = int(width * self.wb_config.roi[2])
        y2 = int(height * self.wb_config.roi[3])
        return x1, y1, x2, y2

    def _is_valid_white_reference(self, roi: np.ndarray) -> bool:
        """ROI が白基準として有効かチェック."""
        # 明度チェック
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)
        if mean_brightness < 50 or mean_brightness > 250:
            logger.debug(f"ROI の明度が不適切: {mean_brightness}")
            return False

        # 彩度チェック (Lab 色空間)
        lab = cv2.cvtColor(roi, cv2.COLOR_BGR2Lab).astype(np.float32)
        a_channel = lab[:, :, 1] - 128
        b_channel = lab[:, :, 2] - 128

        # 平均値を計算
        mean_a = np.mean(np.abs(a_channel))
        mean_b = np.mean(np.abs(b_channel))

        if mean_a > 10 or mean_b > 10:
            logger.debug(f"ROI の彩度が高すぎます: a={mean_a}, b={mean_b}")
            return False

        return True

    def _find_white_reference_auto(self, image: np.ndarray) -> Optional[np.ndarray]:
        """自動的に白基準領域を検出."""
        # Lab 色空間に変換
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2Lab).astype(np.float32)

        # しきい値でマスクを作成
        l_channel = lab[:, :, 0]
        a_channel = np.abs(lab[:, :, 1] - 128)
        b_channel = np.abs(lab[:, :, 2] - 128)

        threshold = self.wb_config.fallback_lab_threshold
        mask = (
            (l_channel >= threshold["l_min"])
            & (l_channel <= threshold["l_max"])
            & (a_channel <= threshold["a_max"])
            & (b_channel <= threshold["b_max"])
        )

        # 最大の連続領域を見つける
        mask_uint8 = mask.astype(np.uint8) * 255
        contours, _ = cv2.findContours(
            mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            logger.warning("白基準となる領域が見つかりませんでした")
            return None

        # 最大面積の領域を選択
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)

        # 最低サイズチェック
        if w < 20 or h < 20:
            logger.warning("検出された白基準領域が小さすぎます")
            return None

        roi = image[y : y + h, x : x + w]
        logger.debug(f"自動検出された白基準領域: ({x}, {y}, {w}, {h})")
        return roi

    def apply_white_balance(self, image: np.ndarray) -> np.ndarray:
        """ホワイトバランス補正を適用."""
        # まず固定 ROI を試す
        x1, y1, x2, y2 = self._get_roi_coordinates(image.shape)
        roi = image[y1:y2, x1:x2]

        if not self._is_valid_white_reference(roi):
            logger.warning("固定 ROI が無効です。自動検出を試みます")
            roi = self._find_white_reference_auto(image)
            if roi is None:
                logger.warning("ホワイトバランス補正をスキップします")
                return image.copy()

        # ROI の平均色を計算
        mean_color = cv2.mean(roi)[:3]  # B, G, R
        logger.debug(
            f"白基準の平均色: B={mean_color[0]:.1f}, G={mean_color[1]:.1f}, R={mean_color[2]:.1f}"
        )

        # グレーの目標値（RGB の平均）
        gray_value = sum(mean_color) / 3

        # 各チャンネルのゲインを計算
        gains = [gray_value / c if c > 0 else 1.0 for c in mean_color]

        # ゲインを適用（飽和を防ぐため clip）
        result = image.astype(np.float32)
        for i in range(3):
            result[:, :, i] *= gains[i]

        result = np.clip(result, 0, 255).astype(np.uint8)

        logger.debug(
            f"ホワイトバランス補正を適用しました。ゲイン: B={gains[0]:.3f}, G={gains[1]:.3f}, R={gains[2]:.3f}"
        )
        return result

    def adjust_tone(self, image: np.ndarray) -> np.ndarray:
        """彩度とコントラストを調整."""
        # HSV 色空間で彩度調整
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] *= self.tone_config.saturation
        hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)

        # BGR に戻す
        result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        # コントラストと明度調整
        result = result.astype(np.float32)
        result = (
            (result - 128) * self.tone_config.contrast
            + 128
            + self.tone_config.brightness
        )
        result = np.clip(result, 0, 255).astype(np.uint8)

        logger.debug(
            f"色調整を適用しました。彩度={self.tone_config.saturation:.2f}, "
            f"コントラスト={self.tone_config.contrast:.2f}, "
            f"明度={self.tone_config.brightness:+.0f}"
        )
        return result

    def process_image(
        self,
        image: Union[np.ndarray, Image.Image, str, bytes],
        apply_wb: bool = True,
        apply_tone: bool = True,
    ) -> np.ndarray:
        """画像を処理.

        Args:
            image: 入力画像
                - np.ndarray: BGR または RGB 形式（内部で BGR として処理）
                - Image.Image: PIL 画像（RGB 形式、自動的に BGR に変換）
                - str: ファイルパス
                - bytes: 画像データのバイト列
            apply_wb: ホワイトバランス補正を適用
            apply_tone: 色調整を適用

        Returns:
            処理済画像（BGR 形式の numpy 配列）

        Note:
            - 入力が PIL Image の場合、RGB → BGR 変換が自動的に行われます
            - 出力は常に BGR 形式の numpy 配列です
            - RGB 形式が必要な場合は cv2.cvtColor(result, cv2.COLOR_BGR2RGB) で変換してください

        """
        # 入力を numpy 配列に変換
        if isinstance(image, str):
            # ファイルパス
            cv_image = cv2.imread(image, cv2.IMREAD_COLOR)
            if cv_image is None:
                raise ValueError(f"画像の読み込みに失敗しました: {image}")
        elif isinstance(image, bytes):
            # バイト列
            nparr = np.frombuffer(image, np.uint8)
            cv_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if cv_image is None:
                raise ValueError("バイト列から画像のデコードに失敗しました")
        elif isinstance(image, Image.Image):
            # PIL Image
            cv_image = convert_pil_to_cv2(image)
        elif isinstance(image, np.ndarray):
            cv_image = image.copy()
        else:
            raise ValueError(f"サポートされていない画像型: {type(image)}")

        # ホワイトバランス補正
        if apply_wb:
            cv_image = self.apply_white_balance(cv_image)

        # 色調整
        if apply_tone:
            cv_image = self.adjust_tone(cv_image)

        return cv_image

    def process_and_save(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        suffix: str = "_processed",
        apply_wb: bool = True,
        apply_tone: bool = True,
        quality: int = 85,
    ) -> str:
        """画像を処理して保存."""
        # 出力パスの決定
        if output_path is None:
            input_p = Path(input_path)
            output_path = str(
                input_p.parent / f"{input_p.stem}{suffix}{input_p.suffix}"
            )

        # 画像処理
        result = self.process_image(
            input_path, apply_wb=apply_wb, apply_tone=apply_tone
        )

        # 保存
        cv2.imwrite(output_path, result, [cv2.IMWRITE_JPEG_QUALITY, quality])
        logger.info(f"処理済画像を保存しました: {output_path}")

        return output_path


def create_default_config(output_path: str = "wb_config.json"):
    """デフォルト設定ファイルを作成."""
    processor = ImageColorProcessor()
    processor.save_config(output_path)
    print(f"デフォルト設定ファイルを作成しました: {output_path}")


if __name__ == "__main__":
    # コマンドライン実行用の簡単なテスト
    import sys

    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python wb_and_tone.py <画像ファイル> [設定ファイル]")
        print("  python wb_and_tone.py --create-config [出力パス]")
        sys.exit(1)

    if sys.argv[1] == "--create-config":
        config_path = sys.argv[2] if len(sys.argv) > 2 else "wb_config.json"
        create_default_config(config_path)
    else:
        input_image = sys.argv[1]
        config_path = sys.argv[2] if len(sys.argv) > 2 else None

        processor = ImageColorProcessor(config_path)

        # ホワイトバランスのみ
        output_wb = processor.process_and_save(
            input_image, suffix="_wb", apply_wb=True, apply_tone=False
        )
        print(f"ホワイトバランス補正済: {output_wb}")

        # ホワイトバランス + 色調整
        output_full = processor.process_and_save(
            input_image, suffix="_wb_tuned", apply_wb=True, apply_tone=True
        )
        print(f"完全処理済: {output_full}")
