"""袖検出の詳細分析スクリプト
なぜ袖が完全に検出されないのかを調査.
"""

import os
import sys
import numpy as np
import cv2
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from coordinate_recorder.complete_inner_extractor import CompleteInnerExtractor


def analyze_color_distribution(image, title="Color Distribution"):
    """色分布の分析."""
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

    fig, axes = plt.subplots(2, 3, figsize=(15, 10))

    # 元画像
    axes[0, 0].imshow(image)
    axes[0, 0].set_title("Original Image")
    axes[0, 0].axis("off")

    # HSV チャンネル
    axes[0, 1].imshow(hsv[:, :, 0], cmap="hsv")
    axes[0, 1].set_title("Hue Channel")
    axes[0, 1].axis("off")

    axes[0, 2].imshow(hsv[:, :, 1], cmap="gray")
    axes[0, 2].set_title("Saturation Channel")
    axes[0, 2].axis("off")

    # 緑色の範囲でマスク
    # 標準範囲
    lower_green = np.array([35, 30, 30])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)

    # より広い範囲
    lower_wide = np.array([30, 20, 20])
    upper_wide = np.array([90, 255, 255])
    green_mask_wide = cv2.inRange(hsv, lower_wide, upper_wide)

    # さらに広い範囲（明るさも考慮）
    lower_very_wide = np.array([25, 15, 15])
    upper_very_wide = np.array([95, 255, 255])
    green_mask_very_wide = cv2.inRange(hsv, lower_very_wide, upper_very_wide)

    axes[1, 0].imshow(green_mask, cmap="gray")
    axes[1, 0].set_title("Standard Green Range\n[35-85, 30-255, 30-255]")
    axes[1, 0].axis("off")

    axes[1, 1].imshow(green_mask_wide, cmap="gray")
    axes[1, 1].set_title("Wide Green Range\n[30-90, 20-255, 20-255]")
    axes[1, 1].axis("off")

    axes[1, 2].imshow(green_mask_very_wide, cmap="gray")
    axes[1, 2].set_title("Very Wide Green Range\n[25-95, 15-255, 15-255]")
    axes[1, 2].axis("off")

    fig.suptitle(title)
    plt.tight_layout()

    return green_mask, green_mask_wide, green_mask_very_wide


def analyze_sleeve_regions(image, mask):
    """袖領域の詳細分析."""
    h, w = image.shape[:2]

    fig, axes = plt.subplots(2, 4, figsize=(16, 8))

    # 全体画像
    axes[0, 0].imshow(image)
    axes[0, 0].set_title("Full Image")
    axes[0, 0].axis("off")

    axes[1, 0].imshow(mask, cmap="gray")
    axes[1, 0].set_title("Full Mask")
    axes[1, 0].axis("off")

    # 左袖候補領域
    left_roi = image[: h // 2, : w // 3]
    left_mask = mask[: h // 2, : w // 3]

    axes[0, 1].imshow(left_roi)
    axes[0, 1].set_title(f"Left Sleeve Region\n{left_roi.shape}")
    axes[0, 1].axis("off")

    axes[1, 1].imshow(left_mask, cmap="gray")
    axes[1, 1].set_title(f"Left Mask\nPixels: {np.sum(left_mask > 0)}")
    axes[1, 1].axis("off")

    # 中央領域
    center_roi = image[:, w // 3 : 2 * w // 3]
    center_mask = mask[:, w // 3 : 2 * w // 3]

    axes[0, 2].imshow(center_roi)
    axes[0, 2].set_title(f"Center Region\n{center_roi.shape}")
    axes[0, 2].axis("off")

    axes[1, 2].imshow(center_mask, cmap="gray")
    axes[1, 2].set_title(f"Center Mask\nPixels: {np.sum(center_mask > 0)}")
    axes[1, 2].axis("off")

    # 右袖候補領域
    right_roi = image[: h // 2, 2 * w // 3 :]
    right_mask = mask[: h // 2, 2 * w // 3 :]

    axes[0, 3].imshow(right_roi)
    axes[0, 3].set_title(f"Right Sleeve Region\n{right_roi.shape}")
    axes[0, 3].axis("off")

    axes[1, 3].imshow(right_mask, cmap="gray")
    axes[1, 3].set_title(f"Right Mask\nPixels: {np.sum(right_mask > 0)}")
    axes[1, 3].axis("off")

    plt.tight_layout()
    return left_roi, center_roi, right_roi


def detect_sleeves_with_edge_analysis(image):
    """エッジ検出を使った袖の検出."""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    # エッジ検出
    edges = cv2.Canny(gray, 50, 150)

    # 色マスクも取得
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    lower_green = np.array([25, 15, 15])
    upper_green = np.array([95, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)

    # エッジと色の組み合わせ
    combined = cv2.bitwise_and(edges, green_mask)

    # 膨張で連結
    kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(combined, kernel, iterations=2)

    fig, axes = plt.subplots(2, 3, figsize=(15, 10))

    axes[0, 0].imshow(image)
    axes[0, 0].set_title("Original")
    axes[0, 0].axis("off")

    axes[0, 1].imshow(edges, cmap="gray")
    axes[0, 1].set_title("Edges (Canny)")
    axes[0, 1].axis("off")

    axes[0, 2].imshow(green_mask, cmap="gray")
    axes[0, 2].set_title("Color Mask")
    axes[0, 2].axis("off")

    axes[1, 0].imshow(combined, cmap="gray")
    axes[1, 0].set_title("Edges & Color")
    axes[1, 0].axis("off")

    axes[1, 1].imshow(dilated, cmap="gray")
    axes[1, 1].set_title("Dilated Combined")
    axes[1, 1].axis("off")

    # 連結成分分析
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated)

    # 大きな成分を可視化
    large_components = np.zeros_like(dilated)
    min_area = 500  # 最小面積

    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] > min_area:
            large_components[labels == i] = 255

    axes[1, 2].imshow(large_components, cmap="gray")
    axes[1, 2].set_title(f"Large Components (>{min_area} px)")
    axes[1, 2].axis("off")

    plt.tight_layout()

    return dilated, large_components


def test_manual_sleeve_detection(image, extractor):
    """手動で袖の位置を指定してテスト."""
    h, w = image.shape[:2]

    # より正確な袖の位置（視覚的に確認して調整）
    sleeve_points = [
        # 左袖（画像の左側）
        (int(w * 0.1), int(h * 0.25)),
        (int(w * 0.2), int(h * 0.3)),
        (int(w * 0.05), int(h * 0.35)),
        # 右袖（画像の右側）
        (int(w * 0.9), int(h * 0.25)),
        (int(w * 0.8), int(h * 0.3)),
        (int(w * 0.95), int(h * 0.35)),
        # 胴体
        (int(w * 0.5), int(h * 0.4)),
        (int(w * 0.5), int(h * 0.5)),
        (int(w * 0.5), int(h * 0.6)),
    ]

    # 抽出実行
    mask, metadata = extractor.extract_complete_inner_layer(
        image, interactive_points=sleeve_points
    )

    # 結果の可視化
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # ポイント付き画像
    axes[0].imshow(image)
    for i, (x, y) in enumerate(sleeve_points):
        color = "red" if i < 3 else "blue" if i < 6 else "green"
        label = "Left" if i < 3 else "Right" if i < 6 else "Body"
        axes[0].plot(
            x, y, "o", color=color, markersize=8, label=label if i % 3 == 0 else ""
        )
    axes[0].legend()
    axes[0].set_title("Manual Points")
    axes[0].axis("off")

    # マスク
    axes[1].imshow(mask, cmap="gray")
    axes[1].set_title(f"Extraction Mask\nCoverage: {metadata['coverage']:.1%}")
    axes[1].axis("off")

    # 抽出結果
    result = image.copy()
    result[mask == 0] = 255
    axes[2].imshow(result)
    axes[2].set_title("Extracted with Manual Points")
    axes[2].axis("off")

    plt.tight_layout()

    return mask


def main():
    """メイン関数."""
    # テスト画像読み込み
    test_image_path = "tests/test_images/aphoto_20250926_132412.jpg"
    image = cv2.imread(test_image_path)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    print(f"Analyzing image: {image.shape}")

    # 出力ディレクトリ
    output_dir = "tests/sleeve_analysis"
    os.makedirs(output_dir, exist_ok=True)

    # 1. 色分布の分析
    print("\n1. Analyzing color distribution...")
    _ = analyze_color_distribution(image, "Color Distribution Analysis")
    plt.savefig(
        os.path.join(output_dir, "color_distribution.png"), dpi=150, bbox_inches="tight"
    )
    plt.show()
    plt.close()

    # 2. CompleteInnerExtractor での抽出
    print("\n2. Running CompleteInnerExtractor...")
    extractor = CompleteInnerExtractor()
    mask_auto, metadata = extractor.extract_complete_inner_layer(image)

    # 3. 袖領域の詳細分析
    print("\n3. Analyzing sleeve regions...")
    left_roi, center_roi, right_roi = analyze_sleeve_regions(image, mask_auto)
    plt.savefig(
        os.path.join(output_dir, "sleeve_regions.png"), dpi=150, bbox_inches="tight"
    )
    plt.show()
    plt.close()

    # 4. エッジベースの分析
    print("\n4. Edge-based analysis...")
    edge_mask, components = detect_sleeves_with_edge_analysis(image)
    plt.savefig(
        os.path.join(output_dir, "edge_analysis.png"), dpi=150, bbox_inches="tight"
    )
    plt.show()
    plt.close()

    # 5. 手動ポイント指定
    print("\n5. Testing with manual points...")
    manual_mask = test_manual_sleeve_detection(image, extractor)
    plt.savefig(
        os.path.join(output_dir, "manual_points_result.png"),
        dpi=150,
        bbox_inches="tight",
    )
    plt.show()
    plt.close()

    # 6. 統計情報
    print("\n=== Detection Statistics ===")
    print(f"Automatic detection coverage: {np.mean(mask_auto > 0):.1%}")
    print(f"Manual points coverage: {np.mean(manual_mask > 0):.1%}")

    # 領域別の統計
    h, w = mask_auto.shape
    regions = {
        "Left third": mask_auto[:, : w // 3],
        "Center third": mask_auto[:, w // 3 : 2 * w // 3],
        "Right third": mask_auto[:, 2 * w // 3 :],
        "Upper half": mask_auto[: h // 2, :],
        "Lower half": mask_auto[h // 2 :, :],
    }

    print("\nRegion-wise pixel counts:")
    for name, region in regions.items():
        pixels = np.sum(region > 0)
        percentage = pixels / region.size * 100
        print(f"  {name}: {pixels:,} pixels ({percentage:.1f}%)")

    print(f"\nResults saved to: {output_dir}")


if __name__ == "__main__":
    main()
