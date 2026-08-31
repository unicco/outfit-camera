"""Co-occurrence data recording and learning service."""

import logging
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .co_occurrence_models import (
    CategoryCoOccurrence,
    DailyOutfitLog,
    ItemPairCoOccurrence,
)
from .wardrobe_models import ClothingItem

logger = logging.getLogger(__name__)


class CoOccurrenceService:
    """共起データの記録と学習を管理するサービス."""

    def __init__(self, session: Session):
        self.session = session

    def record_outfit_wearing(
        self,
        photo_id: Optional[str],
        worn_item_ids: List[str],
        capture_date: Optional[date] = None,
        occasion: Optional[str] = None,
        user_rating: Optional[int] = None,
    ) -> Optional[DailyOutfitLog]:
        """着用記録を保存し、共起データを更新.

        Args:
            photo_id: 写真ID（写真なしの場合は None）
            worn_item_ids: 着用アイテムのIDリスト
            capture_date: 撮影日（省略時は今日）
            occasion: 着用シーン
            user_rating: ユーザー評価 (1-5)

        Returns:
            作成された DailyOutfitLog または None

        Raises:
            ValueError: worn_item_ids が空の場合

        """
        if not worn_item_ids:
            logger.warning(f"Empty worn_item_ids provided for photo {photo_id}")
            raise ValueError("worn_item_ids cannot be empty")

        if not capture_date:
            capture_date = date.today()

        # 着用アイテムの詳細を取得
        worn_items = (
            self.session.query(ClothingItem)
            .filter(ClothingItem.id.in_(worn_item_ids))
            .all()
        )

        if not worn_items:
            logger.warning(f"No valid items found for IDs: {worn_item_ids}")
            return None

        # 部分的に見つからないアイテムがある場合の警告
        if len(worn_items) < len(worn_item_ids):
            found_ids = {item.id for item in worn_items}
            missing_ids = set(worn_item_ids) - found_ids
            logger.warning(f"Some items not found: {missing_ids}")

        # カテゴリ集計
        worn_categories = {}
        for item in worn_items:
            category = item.category.value if item.category else "OTHER"
            worn_categories[category] = worn_categories.get(category, 0) + 1

        # 日次ログを作成
        outfit_log = DailyOutfitLog(
            capture_date=capture_date,
            photo_id=photo_id,
            worn_item_ids=[item.id for item in worn_items],
            worn_categories=worn_categories,
            occasion=occasion,
            user_rating=user_rating,
        )
        self.session.add(outfit_log)

        # アイテムペアの共起を更新
        self._update_item_pair_co_occurrences(worn_items, capture_date)

        # カテゴリレベルの共起を更新
        self._update_category_co_occurrences(worn_items, capture_date)

        try:
            self.session.commit()
            logger.info(
                f"Recorded outfit for {len(worn_items)} items on {capture_date}"
            )
            return outfit_log
        except IntegrityError as e:
            self.session.rollback()
            logger.error(f"Failed to record outfit: {e}")
            raise

    def _update_item_pair_co_occurrences(
        self, worn_items: List[ClothingItem], wear_date: date
    ):
        """アイテムペアの共起データを更新."""
        item_count = len(worn_items)
        if item_count < 2:
            return

        # 全てのペアを生成（順序を正規化）
        for i in range(item_count):
            for j in range(i + 1, item_count):
                item1, item2 = worn_items[i], worn_items[j]
                # IDを辞書順でソート（一貫性のため）
                id1, id2 = sorted([item1.id, item2.id])

                # 既存のレコードを検索または作成
                co_occurrence = (
                    self.session.query(ItemPairCoOccurrence)
                    .filter(
                        ItemPairCoOccurrence.item_id_1 == id1,
                        ItemPairCoOccurrence.item_id_2 == id2,
                    )
                    .first()
                )

                if co_occurrence:
                    # 既存レコードを更新
                    co_occurrence.co_occurrence_count += 1
                    co_occurrence.last_worn_date = wear_date
                    # 信頼度スコアを再計算（単純な例：回数に基づく）
                    co_occurrence.confidence_score = min(
                        1.0, co_occurrence.co_occurrence_count / 10.0
                    )
                else:
                    # 新規レコードを作成
                    co_occurrence = ItemPairCoOccurrence(
                        item_id_1=id1,
                        item_id_2=id2,
                        co_occurrence_count=1,
                        last_worn_date=wear_date,
                        confidence_score=0.1,  # 初期値
                    )
                    self.session.add(co_occurrence)

    def _update_category_co_occurrences(
        self, worn_items: List[ClothingItem], wear_date: date
    ):
        """カテゴリレベルの共起データを更新."""
        # 現在の季節を判定
        season = self._get_season(wear_date)

        # カテゴリとサブカテゴリのペアを収集
        category_pairs = []
        for i in range(len(worn_items)):
            for j in range(i + 1, len(worn_items)):
                item1, item2 = worn_items[i], worn_items[j]
                cat1 = item1.category.value if item1.category else "OTHER"
                cat2 = item2.category.value if item2.category else "OTHER"
                subcat1 = item1.subcategory or ""
                subcat2 = item2.subcategory or ""

                # カテゴリを辞書順でソート
                if cat1 > cat2:
                    cat1, cat2 = cat2, cat1
                    subcat1, subcat2 = subcat2, subcat1

                category_pairs.append((cat1, cat2, subcat1, subcat2))

        # カテゴリペアごとに更新
        for cat1, cat2, subcat1, subcat2 in category_pairs:
            # 全季節と特定季節の両方を更新
            for target_season in ["", season]:  # 空文字列は全季節の統計
                co_occurrence = (
                    self.session.query(CategoryCoOccurrence)
                    .filter(
                        CategoryCoOccurrence.category_1 == cat1,
                        CategoryCoOccurrence.category_2 == cat2,
                        CategoryCoOccurrence.subcategory_1 == subcat1,
                        CategoryCoOccurrence.subcategory_2 == subcat2,
                        CategoryCoOccurrence.season == target_season,
                    )
                    .first()
                )

                if co_occurrence:
                    co_occurrence.co_occurrence_count += 1
                    co_occurrence.total_occurrences += 1
                    # 確率を再計算
                    co_occurrence.probability = (
                        co_occurrence.co_occurrence_count
                        / co_occurrence.total_occurrences
                    )
                else:
                    co_occurrence = CategoryCoOccurrence(
                        category_1=cat1,
                        category_2=cat2,
                        subcategory_1=subcat1,
                        subcategory_2=subcat2,
                        season=target_season,
                        co_occurrence_count=1,
                        total_occurrences=1,
                        probability=1.0,
                    )
                    self.session.add(co_occurrence)

    def _get_season(self, target_date: date) -> str:
        """日付から季節を判定."""
        month = target_date.month
        if month in [3, 4, 5]:
            return "spring"
        elif month in [6, 7, 8]:
            return "summer"
        elif month in [9, 10, 11]:
            return "autumn"
        else:
            return "winter"

    def get_item_pair_score(self, item_id_1: str, item_id_2: str) -> Optional[float]:
        """特定のアイテムペアの共起スコアを取得.

        Returns:
            信頼度スコア (0-1) または None

        """
        # IDを正規化
        id1, id2 = sorted([item_id_1, item_id_2])

        co_occurrence = (
            self.session.query(ItemPairCoOccurrence)
            .filter(
                ItemPairCoOccurrence.item_id_1 == id1,
                ItemPairCoOccurrence.item_id_2 == id2,
            )
            .first()
        )

        return co_occurrence.confidence_score if co_occurrence else None

    def get_category_probability(
        self,
        category_1: str,
        category_2: str,
        subcategory_1: Optional[str] = None,
        subcategory_2: Optional[str] = None,
        season: Optional[str] = None,
    ) -> float:
        """カテゴリペアの共起確率を取得.

        Returns:
            共起確率 (0-1)

        """
        # カテゴリを正規化
        if category_1 > category_2:
            category_1, category_2 = category_2, category_1
            subcategory_1, subcategory_2 = subcategory_2, subcategory_1

        # クエリ条件を構築
        filters = [
            CategoryCoOccurrence.category_1 == category_1,
            CategoryCoOccurrence.category_2 == category_2,
        ]

        if subcategory_1 and subcategory_2:
            filters.extend(
                [
                    CategoryCoOccurrence.subcategory_1 == subcategory_1,
                    CategoryCoOccurrence.subcategory_2 == subcategory_2,
                ]
            )
        else:
            filters.extend(
                [
                    CategoryCoOccurrence.subcategory_1 == "",
                    CategoryCoOccurrence.subcategory_2 == "",
                ]
            )

        if season:
            filters.append(CategoryCoOccurrence.season == season)
        else:
            filters.append(CategoryCoOccurrence.season == "")

        co_occurrence = (
            self.session.query(CategoryCoOccurrence).filter(and_(*filters)).first()
        )

        return co_occurrence.probability if co_occurrence else 0.0

    def get_best_matching_items(
        self, item_id: str, limit: int = 10, min_confidence: float = 0.3
    ) -> List[Tuple[ClothingItem, float]]:
        """指定アイテムと相性の良いアイテムを取得.

        Args:
            item_id: 基準となるアイテムID
            limit: 取得する最大件数
            min_confidence: 最小信頼度スコア

        Returns:
            (ClothingItem, スコア) のリスト

        """
        # アイテムが item_id_1 または item_id_2 として登録されている共起データを取得
        co_occurrences = (
            self.session.query(ItemPairCoOccurrence, ClothingItem)
            .join(
                ClothingItem,
                or_(
                    and_(
                        ItemPairCoOccurrence.item_id_1 == item_id,
                        ItemPairCoOccurrence.item_id_2 == ClothingItem.id,
                    ),
                    and_(
                        ItemPairCoOccurrence.item_id_2 == item_id,
                        ItemPairCoOccurrence.item_id_1 == ClothingItem.id,
                    ),
                ),
            )
            .filter(ItemPairCoOccurrence.confidence_score >= min_confidence)
            .order_by(ItemPairCoOccurrence.confidence_score.desc())
            .limit(limit)
            .all()
        )

        return [(item, co_occur.confidence_score) for co_occur, item in co_occurrences]
