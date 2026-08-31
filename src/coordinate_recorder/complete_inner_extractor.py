"""完全な内側レイヤー抽出モジュール
袖を含めた長袖カットソーの抽出.
"""

import logging
from typing import Optional, Tuple, Dict, Any, List
import numpy as np
import cv2

from .mobile_sam_segmenter import MobileSAMSegmenter

logger = logging.getLogger(__name__)


class CompleteInnerExtractor:
    """袖を含む完全な内側レイヤー抽出クラス."""

    def __init__(self):
        """初期化."""
        self.sam_segmenter = MobileSAMSegmenter()

    def extract_complete_inner_layer(
        self,
        image: np.ndarray,
        initial_bbox: Optional[Dict[str, float]] = None,
        interactive_points: Optional[List[Tuple[int, int]]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """完全な内側レイヤーを抽出.

        Args:
            image: 入力画像 (RGB)
            initial_bbox: 初期バウンディングボックス（オプション）
            interactive_points: ユーザー指定のポイント（袖など）

        Returns:
            抽出されたマスク、メタデータ

        """
        h, w = image.shape[:2]

        # ステップ1: 色ベースの初期検出
        body_mask = self._detect_body_region(image)

        # ステップ2: 袖領域の推定
        sleeve_masks = self._detect_sleeve_regions(image, body_mask)

        # ステップ3: SAMによる統合
        if interactive_points:
            # ユーザー指定のポイントがある場合
            complete_mask = self._integrate_with_user_points(
                image, body_mask, sleeve_masks, interactive_points
            )
        else:
            # 自動検出
            complete_mask = self._integrate_automatically(
                image, body_mask, sleeve_masks
            )

        # ステップ4: 後処理
        final_mask = self._postprocess_mask(complete_mask)

        # メタデータ
        metadata = {
            "method": "CompleteInnerExtractor",
            "has_sleeves": len(sleeve_masks) > 0,
            "interactive": interactive_points is not None,
            "coverage": np.mean(final_mask > 0),
        }

        return final_mask, metadata

    def _detect_body_region(self, image: np.ndarray) -> np.ndarray:
        """胴体部分の検出（既存の色ベース手法）."""
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

        # 緑色の範囲
        lower_green = np.array([35, 30, 30])
        upper_green = np.array([85, 255, 255])

        # マスク作成
        green_mask = cv2.inRange(hsv, lower_green, upper_green)

        # ノイズ除去
        kernel = np.ones((5, 5), np.uint8)
        green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel)
        green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        # 最大連結成分
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(green_mask)

        if num_labels > 1:
            largest_idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
            green_mask = (labels == largest_idx).astype(np.uint8) * 255

        return green_mask

    def _detect_sleeve_regions(
        self, image: np.ndarray, body_mask: np.ndarray
    ) -> List[np.ndarray]:
        """袖領域の検出."""
        h, w = image.shape[:2]
        sleeve_masks = []

        # 胴体の輪郭から袖の開始点を推定
        contours, _ = cv2.findContours(
            body_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return sleeve_masks

        main_contour = max(contours, key=cv2.contourArea)

        # バウンディングボックス
        x, y, width, height = cv2.boundingRect(main_contour)

        # 袖の探索領域を定義（左右）
        sleeve_regions = [
            # 左袖（画像右側）
            {
                "x_start": x + width,
                "x_end": min(w, x + width + width // 2),
                "y_start": y,
                "y_end": y + height // 2,
            },
            # 右袖（画像左側）
            {
                "x_start": max(0, x - width // 2),
                "x_end": x,
                "y_start": y,
                "y_end": y + height // 2,
            },
        ]

        # 各領域で色を探索
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

        for region in sleeve_regions:
            # 領域内で緑色を探索
            roi = hsv[
                region["y_start"] : region["y_end"], region["x_start"] : region["x_end"]
            ]

            if roi.size == 0:
                continue

            # より寛容な緑色範囲
            lower = np.array([30, 20, 20])
            upper = np.array([90, 255, 255])

            sleeve_mask_roi = cv2.inRange(roi, lower, upper)

            # 領域内でのマスク
            if np.sum(sleeve_mask_roi > 0) > 100:  # 最小ピクセル数
                # 全画像サイズのマスクに変換
                full_mask = np.zeros((h, w), dtype=np.uint8)
                full_mask[
                    region["y_start"] : region["y_end"],
                    region["x_start"] : region["x_end"],
                ] = sleeve_mask_roi

                sleeve_masks.append(full_mask)

        return sleeve_masks

    def _integrate_with_user_points(
        self,
        image: np.ndarray,
        body_mask: np.ndarray,
        sleeve_masks: List[np.ndarray],
        user_points: List[Tuple[int, int]],
    ) -> np.ndarray:
        """ユーザー指定ポイントでの統合."""
        if self.sam_segmenter.predictor is None:
            # SAM使用不可の場合
            combined = body_mask.copy()
            for sleeve in sleeve_masks:
                combined = cv2.bitwise_or(combined, sleeve)
            return combined

        # SAMで統合
        self.sam_segmenter.predictor.set_image(image)

        # すべてのマスクから種点を生成
        all_points = list(user_points)

        # 胴体からも点を追加
        body_points = self._sample_points_from_mask(body_mask, 3)
        all_points.extend(body_points)

        # ポイントプロンプト
        point_coords = np.array(all_points)
        point_labels = np.ones(len(all_points), dtype=int)

        masks, scores, _ = self.sam_segmenter.predictor.predict(
            point_coords=point_coords, point_labels=point_labels, multimask_output=True
        )

        # 最も包括的なマスクを選択
        best_mask = self._select_most_complete_mask(masks, scores, body_mask)

        return (best_mask * 255).astype(np.uint8)

    def _integrate_automatically(
        self, image: np.ndarray, body_mask: np.ndarray, sleeve_masks: List[np.ndarray]
    ) -> np.ndarray:
        """自動統合."""
        # 初期統合マスク
        combined = body_mask.copy()

        # 袖マスクを追加
        for sleeve in sleeve_masks:
            combined = cv2.bitwise_or(combined, sleeve)

        if self.sam_segmenter.predictor is None:
            return combined

        # SAMで改良
        seed_points = self._generate_comprehensive_seeds(combined, sleeve_masks)

        if len(seed_points) == 0:
            return combined

        # SAM予測
        self.sam_segmenter.predictor.set_image(image)

        point_coords = np.array(seed_points)
        point_labels = np.ones(len(seed_points), dtype=int)

        masks, scores, _ = self.sam_segmenter.predictor.predict(
            point_coords=point_coords, point_labels=point_labels, multimask_output=True
        )

        # 最適なマスクを選択
        best_mask = self._select_best_complete_mask(masks, scores, combined, image)

        if best_mask is not None:
            return (best_mask * 255).astype(np.uint8)

        return combined

    def _sample_points_from_mask(
        self, mask: np.ndarray, num_points: int
    ) -> List[Tuple[int, int]]:
        """マスクから代表点をサンプリング."""
        points = []

        # マスクの輪郭を検出
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return points

        contour = max(contours, key=cv2.contourArea)

        # 重心
        M = cv2.moments(contour)
        if M["m00"] > 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            points.append((cx, cy))

        # バウンディングボックスの端点
        x, y, w, h = cv2.boundingRect(contour)

        if num_points >= 3:
            points.append((x + w // 2, y + h // 4))  # 上部
            points.append((x + w // 2, y + 3 * h // 4))  # 下部

        if num_points >= 5:
            points.append((x + w // 4, y + h // 2))  # 左
            points.append((x + 3 * w // 4, y + h // 2))  # 右

        return points[:num_points]

    def _generate_comprehensive_seeds(
        self, combined_mask: np.ndarray, sleeve_masks: List[np.ndarray]
    ) -> List[Tuple[int, int]]:
        """包括的な種点を生成."""
        points = []

        # 胴体から
        body_points = self._sample_points_from_mask(combined_mask, 3)
        points.extend(body_points)

        # 各袖から
        for sleeve in sleeve_masks:
            sleeve_points = self._sample_points_from_mask(sleeve, 2)
            points.extend(sleeve_points)

        return points

    def _select_most_complete_mask(
        self, masks: np.ndarray, scores: np.ndarray, reference_mask: np.ndarray
    ) -> np.ndarray:
        """最も完全なマスクを選択."""
        best_mask = None
        best_score = -1

        for mask, score in zip(masks, scores):
            # 参照マスクとの重なり
            overlap = np.logical_and(mask, reference_mask > 0)
            overlap_ratio = np.sum(overlap) / (np.sum(reference_mask > 0) + 1e-6)

            # マスクの面積
            mask_area = np.sum(mask)

            # 総合スコア
            total_score = (
                score * 0.3 + overlap_ratio * 0.3 + (mask_area / mask.size) * 0.4
            )

            if total_score > best_score:
                best_score = total_score
                best_mask = mask

        return best_mask

    def _select_best_complete_mask(
        self,
        masks: np.ndarray,
        scores: np.ndarray,
        reference_mask: np.ndarray,
        image: np.ndarray,
    ) -> Optional[np.ndarray]:
        """最適な完全マスクを選択."""
        best_mask = None
        best_score = -1

        # HSVで色を確認
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

        for mask, score in zip(masks, scores):
            # 参照マスクとの重なり
            overlap_ratio = np.sum(np.logical_and(mask, reference_mask > 0)) / (
                np.sum(reference_mask > 0) + 1e-6
            )

            # 緑色の保持率
            masked_hsv = hsv[mask]
            if len(masked_hsv) > 0:
                green_mask = (masked_hsv[:, 0] > 30) & (masked_hsv[:, 0] < 90)
                green_ratio = np.mean(green_mask)
            else:
                green_ratio = 0

            # マスクの連続性
            num_labels, _ = cv2.connectedComponents(mask.astype(np.uint8))
            continuity = 1.0 / num_labels if num_labels > 0 else 0

            # 総合スコア
            total_score = (
                score * 0.2 + overlap_ratio * 0.3 + green_ratio * 0.3 + continuity * 0.2
            )

            if total_score > best_score and green_ratio > 0.3:
                best_score = total_score
                best_mask = mask

        return best_mask

    def _postprocess_mask(self, mask: np.ndarray) -> np.ndarray:
        """マスクの後処理."""
        # 穴を埋める
        kernel_close = np.ones((7, 7), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=2)

        # 小さなノイズを除去
        kernel_open = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)

        # エッジを滑らかに
        mask = cv2.medianBlur(mask, 5)

        # 最大連結成分のみを保持
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask)

        if num_labels > 1:
            largest_idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
            mask = (labels == largest_idx).astype(np.uint8) * 255

        return mask
