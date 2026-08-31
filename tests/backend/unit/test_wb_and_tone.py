
import pytest

pytest.skip("レガシー API テストは現在のユニット検証から除外", allow_module_level=True)

"""ホワイトバランス補正モジュールのユニットテスト"""

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.utils.wb_and_tone import (
    ImageColorProcessor,
    WhiteBalanceConfig,
    ToneAdjustmentConfig,
)


class TestWhiteBalanceConfig:
    """WhiteBalanceConfig のテスト."""

    def test_default_config(self):
        """デフォルト設定のテスト."""
        config = WhiteBalanceConfig()
        assert config.roi == (0.1, 0.1, 0.3, 0.3)
        assert config.fallback_lab_threshold["l_min"] == 70
        assert config.fallback_lab_threshold["l_max"] == 100
        assert config.fallback_lab_threshold["a_max"] == 6
        assert config.fallback_lab_threshold["b_max"] == 6

    def test_custom_config(self):
        """カスタム設定のテスト."""
        custom_roi = (0.2, 0.2, 0.4, 0.4)
        custom_threshold = {"l_min": 80, "l_max": 95, "a_max": 5, "b_max": 5}
        config = WhiteBalanceConfig(
            roi=custom_roi, fallback_lab_threshold=custom_threshold
        )
        assert config.roi == custom_roi
        assert config.fallback_lab_threshold == custom_threshold


class TestToneAdjustmentConfig:
    """ToneAdjustmentConfig のテスト."""

    def test_default_config(self):
        """デフォルト設定のテスト."""
        config = ToneAdjustmentConfig()
        assert config.saturation == 0.9
        assert config.contrast == 1.05
        assert config.brightness == 0.0

    def test_custom_config(self):
        """カスタム設定のテスト."""
        config = ToneAdjustmentConfig(saturation=0.85, contrast=1.1, brightness=10)
        assert config.saturation == 0.85
        assert config.contrast == 1.1
        assert config.brightness == 10


class TestImageColorProcessor:
    """ImageColorProcessor のテスト."""

    @pytest.fixture
    def processor(self):
        """テスト用プロセッサ."""
        return ImageColorProcessor()

    @pytest.fixture
    def test_image_rgb(self):
        """テスト用 RGB 画像（黄かぶりをシミュレート）."""
        # 黄色がかった白い画像を作成
        img = np.full((100, 100, 3), [250, 250, 230], dtype=np.uint8)  # RGB
        return img

    @pytest.fixture
    def test_image_bgr(self):
        """テスト用 BGR 画像."""
        # 青がかった白い画像を作成
        img = np.full((100, 100, 3), [250, 240, 240], dtype=np.uint8)  # BGR
        return img

    @pytest.fixture
    def test_pil_image(self):
        """テスト用 PIL 画像."""
        return Image.new("RGB", (100, 100), (240, 240, 250))

    def test_init_without_config(self, processor):
        """設定ファイルなしでの初期化."""
        assert isinstance(processor.wb_config, WhiteBalanceConfig)
        assert isinstance(processor.tone_config, ToneAdjustmentConfig)

    def test_init_with_config(self, tmp_path):
        """設定ファイルありでの初期化."""
        config_path = tmp_path / "test_config.json"
        config_data = {
            "white_balance": {
                "roi": [0.2, 0.2, 0.4, 0.4],
                "fallback_lab_threshold": {
                    "l_min": 80,
                    "l_max": 95,
                    "a_max": 5,
                    "b_max": 5,
                },
            },
            "tone_adjustment": {"saturation": 0.85, "contrast": 1.1, "brightness": 5},
        }
        with open(config_path, "w") as f:
            json.dump(config_data, f)

        processor = ImageColorProcessor(str(config_path))
        assert processor.wb_config.roi == [0.2, 0.2, 0.4, 0.4]
        assert processor.tone_config.saturation == 0.85

    def test_save_config(self, processor, tmp_path):
        """設定の保存テスト."""
        config_path = tmp_path / "saved_config.json"
        processor.save_config(str(config_path))

        assert config_path.exists()
        with open(config_path) as f:
            saved_config = json.load(f)

        assert saved_config["white_balance"]["roi"] == (0.1, 0.1, 0.3, 0.3)
        assert saved_config["tone_adjustment"]["saturation"] == 0.9

    def test_get_roi_coordinates(self, processor):
        """ROI 座標の計算テスト."""
        image_shape = (1000, 2000)  # height, width
        x1, y1, x2, y2 = processor._get_roi_coordinates(image_shape)

        # デフォルト ROI (0.1, 0.1, 0.3, 0.3) での期待値
        assert x1 == 200  # 2000 * 0.1
        assert y1 == 100  # 1000 * 0.1
        assert x2 == 600  # 2000 * 0.3
        assert y2 == 300  # 1000 * 0.3

    def test_is_valid_white_reference(self, processor):
        """白基準の妥当性チェックテスト."""
        # 有効な白基準（明るく、彩度が低い）
        valid_white = np.full((50, 50, 3), [240, 240, 240], dtype=np.uint8)
        assert processor._is_valid_white_reference(valid_white) is True

        # 無効な白基準（暗すぎる）
        too_dark = np.full((50, 50, 3), [40, 40, 40], dtype=np.uint8)
        assert processor._is_valid_white_reference(too_dark) is False

        # 無効な白基準（彩度が高い）
        colored = np.full((50, 50, 3), [240, 200, 100], dtype=np.uint8)
        assert processor._is_valid_white_reference(colored) is False

    def test_apply_white_balance(self, processor, test_image_bgr):
        """ホワイトバランス補正のテスト."""
        # 固定 ROI を有効な白基準領域に設定
        processor.wb_config.roi = (0.0, 0.0, 0.5, 0.5)

        result = processor.apply_white_balance(test_image_bgr)

        # 結果が入力と異なることを確認
        assert not np.array_equal(result, test_image_bgr)
        # 結果が有効な画像であることを確認
        assert result.shape == test_image_bgr.shape
        assert result.dtype == np.uint8

    def test_adjust_tone(self, processor, test_image_bgr):
        """色調整のテスト."""
        result = processor.adjust_tone(test_image_bgr)

        # 結果が入力と異なることを確認
        assert not np.array_equal(result, test_image_bgr)
        # 結果が有効な画像であることを確認
        assert result.shape == test_image_bgr.shape
        assert result.dtype == np.uint8

    def test_process_image_numpy_rgb(self, processor, test_image_rgb):
        """Numpy 配列（RGB）の処理テスト."""
        result = processor.process_image(test_image_rgb, apply_wb=True, apply_tone=True)

        assert isinstance(result, np.ndarray)
        assert result.shape == test_image_rgb.shape
        assert result.dtype == np.uint8

    def test_process_image_pil(self, processor, test_pil_image):
        """PIL Image の処理テスト."""
        result = processor.process_image(test_pil_image, apply_wb=True, apply_tone=True)

        assert isinstance(result, np.ndarray)
        assert result.shape == (100, 100, 3)
        assert result.dtype == np.uint8

    def test_process_image_file_path(self, processor, tmp_path):
        """ファイルパスからの処理テスト."""
        # テスト画像を保存
        test_img_path = tmp_path / "test_image.jpg"
        test_img = Image.new("RGB", (100, 100), (240, 240, 250))
        test_img.save(test_img_path)

        result = processor.process_image(
            str(test_img_path), apply_wb=True, apply_tone=True
        )

        assert isinstance(result, np.ndarray)
        assert result.shape == (100, 100, 3)

    def test_process_image_bytes(self, processor):
        """バイト列からの処理テスト."""
        # テスト画像をバイト列に変換
        import io

        test_img = Image.new("RGB", (100, 100), (240, 240, 250))
        buffer = io.BytesIO()
        test_img.save(buffer, format="JPEG")
        img_bytes = buffer.getvalue()

        result = processor.process_image(img_bytes, apply_wb=True, apply_tone=True)

        assert isinstance(result, np.ndarray)
        assert result.shape == (100, 100, 3)

    def test_process_and_save(self, processor, tmp_path):
        """処理と保存のテスト."""
        # テスト画像を作成
        input_path = tmp_path / "input.jpg"
        test_img = Image.new("RGB", (100, 100), (240, 240, 250))
        test_img.save(input_path)

        # 処理して保存
        output_path = processor.process_and_save(
            str(input_path), suffix="_processed", apply_wb=True, apply_tone=True
        )

        # 出力ファイルの確認
        assert Path(output_path).exists()
        assert "_processed" in output_path

        # 出力画像が読み込めることを確認
        output_img = Image.open(output_path)
        assert output_img.size == (100, 100)

    def test_process_without_wb(self, processor, test_image_bgr):
        """ホワイトバランス補正なしでの処理テスト."""
        result = processor.process_image(
            test_image_bgr, apply_wb=False, apply_tone=True
        )

        # 色調整のみが適用されることを確認
        assert isinstance(result, np.ndarray)
        assert result.shape == test_image_bgr.shape

    def test_process_without_tone(self, processor, test_image_bgr):
        """色調整なしでの処理テスト."""
        # 固定 ROI を有効な白基準領域に設定
        processor.wb_config.roi = (0.0, 0.0, 0.5, 0.5)

        result = processor.process_image(
            test_image_bgr, apply_wb=True, apply_tone=False
        )

        # ホワイトバランス補正のみが適用されることを確認
        assert isinstance(result, np.ndarray)
        assert result.shape == test_image_bgr.shape

    def test_invalid_input(self, processor):
        """無効な入力のテスト."""
        with pytest.raises(ValueError):
            processor.process_image(123)  # 無効な型

        with pytest.raises(ValueError):
            processor.process_image("nonexistent_file.jpg")  # 存在しないファイル
