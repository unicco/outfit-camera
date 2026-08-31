"""衣類の詳細属性を検出するサービス.

エッジ検出によるシルエット特徴や、簡易的な袖の長さ判定などを実装。
Issue #1045 の実装。
"""

import cv2
import numpy as np
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class AttributeDetector:
    """衣類の詳細属性を検出するクラス."""

    def __init__(self) -> None:
        """初期化."""
        # HSV色空間での肌色範囲
        self.skin_lower_hsv = np.array([0, 30, 60], dtype=np.uint8)
        self.skin_upper_hsv = np.array([20, 150, 255], dtype=np.uint8)

        # YCrCb色空間での肌色範囲
        self.skin_lower_ycrcb = np.array([80, 135, 80], dtype=np.uint8)
        self.skin_upper_ycrcb = np.array([255, 180, 130], dtype=np.uint8)
        # エッジ検出時の画像サイズを制限（2048^2 ピクセル）
        self._max_edge_pixels = 2048 * 2048

    def detect_attributes(
        self,
        image: np.ndarray,
        category: str,
        colors_palette: Optional[Dict[str, Any]] = None,
        embedding_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """画像から衣類の属性を検出.

        Args:
            image: 検出対象の画像（BGR）
            category: 衣類のカテゴリ（TOPS, BOTTOMS等）
            colors_palette: Issue #1059 で実装された色情報
            embedding_description: 埋め込みの説明文（パターン情報を含む）

        Returns:
            検出された属性の辞書

        """
        attributes: Dict[str, Any] = {}

        # パターンタイプを検出
        pattern_type: Optional[str] = None
        if embedding_description:
            pattern_type = self.detect_pattern_from_embedding(embedding_description)
            attributes["pattern_type"] = pattern_type

        # デザイン複雑性を判定
        if colors_palette:
            design_complexity = self.calculate_design_complexity(colors_palette)
            attributes["design_complexity"] = design_complexity

        # シルエット特徴を抽出（パターンタイプに応じて調整）
        silhouette_features = self.extract_silhouette_features(image, pattern_type)
        attributes["silhouette"] = self._classify_silhouette(silhouette_features)
        attributes["silhouette_features"] = silhouette_features

        # トップスの場合は袖の長さを判定
        if category == "TOPS":
            sleeve_length = self.detect_sleeve_length(image)
            attributes["sleeve_length"] = sleeve_length

        return attributes

    def extract_silhouette_features(
        self, image: np.ndarray, pattern_type: Optional[str] = None
    ) -> Dict[str, float]:
        """エッジ検出によるシルエット特徴の抽出.

        Args:
            image: 入力画像（BGR）
            pattern_type: パターンタイプ（gradient, multicolored等）

        Returns:
            シルエット特徴量の辞書

        """
        features = {
            "aspect_ratio": 1.0,
            "solidity": 1.0,
            "extent": 1.0,
            "compactness": 1.0,
        }

        if image is None or image.size == 0:
            logger.warning("空の画像が渡されたためシルエット抽出をスキップします")
            return features

        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        except cv2.error as exc:
            logger.warning("グレースケール変換に失敗しました: %s", exc)
            return features

        if gray.size > self._max_edge_pixels:
            scale = (self._max_edge_pixels / float(gray.size)) ** 0.5
            new_width = max(1, int(gray.shape[1] * scale))
            new_height = max(1, int(gray.shape[0] * scale))
            gray = cv2.resize(
                gray, (new_width, new_height), interpolation=cv2.INTER_AREA
            )

        try:
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        except cv2.error as exc:
            logger.warning("ガウシアンブラー適用に失敗しました: %s", exc)
            return features

        # Cannyエッジ検出（パターンに応じて閾値を調整）
        if pattern_type in ["gradient", "multicolored", "rainbow"]:
            # グラデーションやマルチカラーの場合は低い閾値
            low_threshold = 30
            high_threshold = 100
        elif pattern_type in ["striped", "checkered", "plaid"]:
            # パターンがある場合は中程度の閾値
            low_threshold = 40
            high_threshold = 120
        else:
            # 通常の閾値
            low_threshold = 50
            high_threshold = 150

        try:
            edges = cv2.Canny(blurred, low_threshold, high_threshold)
        except cv2.error as exc:
            logger.warning("エッジ検出に失敗しました: %s", exc)
            return features

        try:
            contours, _ = cv2.findContours(
                edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
        except cv2.error as exc:
            logger.warning("輪郭検出に失敗しました: %s", exc)
            return features

        if contours:
            # 最大輪郭を取得
            largest_contour = max(contours, key=cv2.contourArea)

            # バウンディングボックス
            x, y, w, h = cv2.boundingRect(largest_contour)

            # アスペクト比（幅/高さ）
            features["aspect_ratio"] = w / h if h > 0 else 1.0

            # 凸包を計算
            hull = cv2.convexHull(largest_contour)
            hull_area = cv2.contourArea(hull)
            contour_area = cv2.contourArea(largest_contour)

            # Solidity（輪郭面積/凸包面積）
            if hull_area > 0:
                features["solidity"] = contour_area / hull_area

            # Extent（輪郭面積/バウンディングボックス面積）
            bbox_area = w * h
            if bbox_area > 0:
                features["extent"] = contour_area / bbox_area

            # Compactness（周囲長の二乗/面積）
            perimeter = cv2.arcLength(largest_contour, True)
            if contour_area > 0:
                features["compactness"] = (perimeter**2) / (4 * np.pi * contour_area)

        return features

    def _classify_silhouette(self, features: Dict[str, float]) -> str:
        """シルエット特徴からシルエットタイプを分類.

        Args:
            features: シルエット特徴量

        Returns:
            シルエットタイプ（tight, regular, loose）

        """
        aspect_ratio = features["aspect_ratio"]
        solidity = features["solidity"]
        extent = features["extent"]

        # 簡易的な分類ルール
        if solidity > 0.95 and extent > 0.8:
            return "tight"
        elif solidity < 0.85 or aspect_ratio > 0.8:
            return "loose"
        else:
            return "regular"

    def detect_sleeve_length(self, image: np.ndarray) -> str:
        """袖の長さを簡易的に判定.

        Args:
            image: トップスの画像（BGR）

        Returns:
            袖の長さ（long_sleeve, short_sleeve, sleeveless）

        """
        height, width = image.shape[:2]

        # 画像を3つの領域に分割して分析
        # 上部：肩の部分
        upper_region = image[0 : int(height * 0.3), :]
        # 中部：袖の部分
        middle_region = image[int(height * 0.3) : int(height * 0.7), :]
        # 下部：裾の部分
        lower_region = image[int(height * 0.7) :, :]

        # 各領域で肌色を検出
        upper_skin_ratio = self._detect_skin_ratio(upper_region)
        middle_skin_ratio = self._detect_skin_ratio(middle_region)
        lower_skin_ratio = self._detect_skin_ratio(lower_region)

        # 左右の端部分（袖の位置）を重点的にチェック
        edge_width = int(width * 0.2)
        left_edge = middle_region[:, :edge_width]
        right_edge = middle_region[:, -edge_width:]

        left_skin_ratio = self._detect_skin_ratio(left_edge)
        right_skin_ratio = self._detect_skin_ratio(right_edge)
        edge_skin_ratio = (left_skin_ratio + right_skin_ratio) / 2

        logger.debug(
            "Sleeve detection ratios upper=%.3f middle=%.3f lower=%.3f edge=%.3f",
            upper_skin_ratio,
            middle_skin_ratio,
            lower_skin_ratio,
            edge_skin_ratio,
        )

        # 分類ロジック
        if upper_skin_ratio > 0.3 or middle_skin_ratio > 0.25:
            # 肩の部分に肌色が多い → ノースリーブ
            return "sleeveless"
        elif edge_skin_ratio > 0.15 or lower_skin_ratio > 0.2:
            # 袖の端に肌色が見える → 半袖
            return "short_sleeve"
        else:
            # それ以外 → 長袖
            return "long_sleeve"

    def _detect_skin_ratio(self, region: np.ndarray) -> float:
        """領域内の肌色の割合を検出.

        Args:
            region: 検出対象の領域（BGR）

        Returns:
            肌色ピクセルの割合（0.0〜1.0）

        """
        # HSV色空間に変換
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        # 肌色の範囲でマスクを作成
        hsv_mask = cv2.inRange(hsv, self.skin_lower_hsv, self.skin_upper_hsv)

        # YCrCb色空間でも検出（より精度を上げるため）
        ycrcb = cv2.cvtColor(region, cv2.COLOR_BGR2YCrCb)
        ycrcb_mask = cv2.inRange(ycrcb, self.skin_lower_ycrcb, self.skin_upper_ycrcb)

        # 両方のマスクを組み合わせる
        combined_mask = cv2.bitwise_or(hsv_mask, ycrcb_mask)

        # ノイズ除去
        kernel = np.ones((3, 3), np.uint8)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)

        # 肌色ピクセルの割合を計算
        total_pixels = region.shape[0] * region.shape[1]
        skin_pixels = np.sum(combined_mask > 0)

        return skin_pixels / total_pixels if total_pixels > 0 else 0.0

    def calculate_silhouette_similarity(
        self,
        features1: Optional[Dict[str, float]],
        features2: Optional[Dict[str, float]],
    ) -> float:
        """2つのシルエット特徴量の類似度を計算.

        Args:
            features1: シルエット特徴量1
            features2: シルエット特徴量2

        Returns:
            類似度（0.0〜1.0）

        """
        if not features1 or not features2:
            return 0.5  # デフォルト値

        # 各特徴量の差分を計算
        aspect_diff = abs(
            features1.get("aspect_ratio", 1.0) - features2.get("aspect_ratio", 1.0)
        )
        solidity_diff = abs(
            features1.get("solidity", 1.0) - features2.get("solidity", 1.0)
        )
        extent_diff = abs(features1.get("extent", 1.0) - features2.get("extent", 1.0))

        # 差分を0〜1の範囲に正規化して類似度に変換
        aspect_sim = 1.0 - min(aspect_diff / 0.5, 1.0)  # 0.5の差を最大とする
        solidity_sim = 1.0 - min(solidity_diff / 0.2, 1.0)  # 0.2の差を最大とする
        extent_sim = 1.0 - min(extent_diff / 0.3, 1.0)  # 0.3の差を最大とする

        # 重み付き平均
        similarity = aspect_sim * 0.4 + solidity_sim * 0.3 + extent_sim * 0.3

        return similarity

    def detect_pattern_from_embedding(
        self, embedding_description: str
    ) -> Optional[str]:
        """埋め込みの説明文からパターンを検出.

        Args:
            embedding_description: 埋め込みの説明文

        Returns:
            検出されたパターンタイプ

        """
        patterns = {
            "striped pattern": "striped",
            "rainbow pattern": "rainbow",
            "gradient design": "gradient",
            "multicolored pattern": "multicolored",
            "checkered": "checkered",
            "plaid": "plaid",
            "floral": "floral",
            "polka dot": "polka_dot",
            "geometric": "geometric",
        }

        description_lower = embedding_description.lower()
        for pattern_key, pattern_value in patterns.items():
            if pattern_key in description_lower:
                return pattern_value

        return None

    def calculate_design_complexity(self, colors_palette: Dict) -> str:
        """色数に基づくデザイン複雑性の判定.

        Args:
            colors_palette: 色情報の辞書

        Returns:
            デザイン複雑性（simple, moderate, complex）

        """
        palette = colors_palette.get("palette", [])

        # 色数に基づく判定
        if len(palette) >= 4:
            return "complex"
        elif len(palette) >= 2:
            return "moderate"
        else:
            return "simple"
