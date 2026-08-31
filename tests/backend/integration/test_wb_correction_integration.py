"""ホワイトバランス補正機能の統合テスト."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.utils.wb_and_tone import ImageColorProcessor


class TestWhiteBalanceCorrectionIntegration:
    """ホワイトバランス補正の統合テスト."""

    @pytest.fixture
    def sample_image_with_yellow_cast(self):
        """黄かぶりのあるテスト画像を生成."""
        # 黄色がかった画像を生成（全体的に黄色い）
        width, height = 400, 300
        img = np.zeros((height, width, 3), dtype=np.uint8)

        # 左上に白基準領域を作成
        img[:100, :100] = [250, 250, 230]  # 黄かぶりの白

        # 中央に色のあるオブジェクト
        img[100:200, 150:250] = [200, 100, 50]  # 茶色っぽい色

        # 背景は薄い黄色
        img[200:, :] = [240, 240, 220]

        return img

    @pytest.fixture
    def sample_image_with_blue_cast(self):
        """青かぶりのあるテスト画像を生成."""
        width, height = 400, 300
        img = np.zeros((height, width, 3), dtype=np.uint8)

        # 左上に白基準領域
        img[:100, :100] = [230, 240, 250]  # 青かぶりの白

        # 中央に色のあるオブジェクト
        img[100:200, 150:250] = [50, 150, 200]  # 青っぽい色

        # 背景は薄い青
        img[200:, :] = [220, 230, 240]

        return img

    def test_end_to_end_yellow_cast_correction(
        self, sample_image_with_yellow_cast, tmp_path
    ):
        """黄かぶり補正のエンドツーエンドテスト."""
        # 設定ファイルを作成
        config_path = tmp_path / "test_config.json"
        processor = ImageColorProcessor()
        processor.save_config(str(config_path))

        # プロセッサを再初期化
        processor = ImageColorProcessor(str(config_path))

        # 画像を処理
        corrected = processor.process_image(
            sample_image_with_yellow_cast, apply_wb=True, apply_tone=True
        )

        # 白基準領域の色を確認
        white_region = corrected[:100, :100]
        mean_color = np.mean(white_region, axis=(0, 1))

        # RGB チャンネルがより均等になっているはず
        r, g, b = mean_color
        color_variance = np.var([r, g, b])

        # 元の画像の色の分散
        original_white = sample_image_with_yellow_cast[:100, :100]
        original_mean = np.mean(original_white, axis=(0, 1))
        original_variance = np.var(original_mean)

        # 補正後の方が色の分散が小さい（より中性的）
        assert color_variance < original_variance

    def test_end_to_end_blue_cast_correction(
        self, sample_image_with_blue_cast, tmp_path
    ):
        """青かぶり補正のエンドツーエンドテスト."""
        processor = ImageColorProcessor()

        # 画像を処理
        corrected = processor.process_image(
            sample_image_with_blue_cast, apply_wb=True, apply_tone=True
        )

        # 白基準領域の色を確認
        white_region = corrected[:100, :100]
        mean_color = np.mean(white_region, axis=(0, 1))

        # RGB チャンネルがより均等になっているはず
        r, g, b = mean_color
        assert abs(r - g) < 20  # チャンネル間の差が小さい
        assert abs(g - b) < 20
        assert abs(r - b) < 20

    def test_saturation_adjustment(self, sample_image_with_yellow_cast):
        """彩度調整のテスト."""
        processor = ImageColorProcessor()

        # 彩度を下げる設定
        processor.tone_config.saturation = 0.5

        # 画像を処理（色調整のみ）
        result = processor.process_image(
            sample_image_with_yellow_cast, apply_wb=False, apply_tone=True
        )

        # HSV に変換して彩度を確認
        import cv2

        original_hsv = cv2.cvtColor(sample_image_with_yellow_cast, cv2.COLOR_RGB2HSV)
        result_hsv = cv2.cvtColor(result, cv2.COLOR_RGB2HSV)

        # 彩度が下がっているはず
        original_saturation = np.mean(original_hsv[:, :, 1])
        result_saturation = np.mean(result_hsv[:, :, 1])

        assert result_saturation < original_saturation

    def test_contrast_adjustment(self, sample_image_with_yellow_cast):
        """コントラスト調整のテスト."""
        processor = ImageColorProcessor()

        # コントラストを上げる設定
        processor.tone_config.contrast = 1.5
        processor.tone_config.saturation = 1.0  # 彩度は変更しない

        # 画像を処理（色調整のみ）
        result = processor.process_image(
            sample_image_with_yellow_cast, apply_wb=False, apply_tone=True
        )

        # 標準偏差（コントラストの指標）を確認
        original_std = np.std(sample_image_with_yellow_cast)
        result_std = np.std(result)

        # コントラストが上がっているはず
        assert result_std > original_std

    def test_fallback_to_auto_roi(self):
        """自動 ROI 検出へのフォールバックテスト."""
        processor = ImageColorProcessor()

        # 無効な ROI を設定（画像の外側）
        processor.wb_config.roi = (0.9, 0.9, 1.0, 1.0)

        # ほぼ白い画像を作成
        img = np.full((100, 100, 3), [240, 240, 240], dtype=np.uint8)

        # エラーなく処理できることを確認
        result = processor.process_image(img, apply_wb=True, apply_tone=False)
        assert result is not None
        assert result.shape == img.shape

    def test_performance_benchmark(self, sample_image_with_yellow_cast):
        """パフォーマンステスト."""
        import time

        processor = ImageColorProcessor()

        # ウォームアップ
        processor.process_image(sample_image_with_yellow_cast)

        # 時間計測
        times = []
        for _ in range(10):
            start = time.time()
            processor.process_image(
                sample_image_with_yellow_cast, apply_wb=True, apply_tone=True
            )
            times.append((time.time() - start) * 1000)  # ms

        avg_time = np.mean(times)

        # ドキュメントに記載の 50-100ms 以内であることを確認
        assert avg_time < 150  # 少し余裕を持たせる

    def test_file_based_workflow(self, tmp_path):
        """ファイルベースのワークフローテスト."""
        # テスト画像を作成して保存
        input_path = tmp_path / "input.jpg"
        img = Image.new("RGB", (200, 200), (250, 250, 230))  # 黄かぶり
        img.save(input_path)

        # 設定ファイルを作成
        config_path = tmp_path / "config.json"
        processor = ImageColorProcessor()
        processor.save_config(str(config_path))

        # 新しいプロセッサで処理
        processor2 = ImageColorProcessor(str(config_path))
        output_path = processor2.process_and_save(
            str(input_path),
            output_path=str(tmp_path / "output.jpg"),
            apply_wb=True,
            apply_tone=True,
        )

        # 出力ファイルが存在することを確認
        assert Path(output_path).exists()

        # 出力画像を読み込んで検証
        output_img = Image.open(output_path)
        assert output_img.size == (200, 200)

        # 色が変化していることを確認
        input_array = np.array(img)
        output_array = np.array(output_img)
        assert not np.array_equal(input_array, output_array)
