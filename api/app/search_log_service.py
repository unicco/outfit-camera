"""Service for logging search results and managing feedback."""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from .search_log_models import SearchLog, SearchResultItem
from .wardrobe_models import ClothingItem

logger = logging.getLogger(__name__)


class SearchLogService:
    """検索結果のログ管理サービス."""

    def __init__(self, session: Session):
        self.session = session

    def log_search_results(
        self,
        capture_id: Optional[str],
        detected_item_id: str,
        detected_category: str,
        detected_embedding: np.ndarray,
        detected_description: str,
        search_results: List[Tuple[Dict[str, Any], float, Dict[str, float]]],
        is_manual: bool = False,
    ) -> SearchLog:
        """検索結果をログに記録.

        Args:
            capture_id: AIキャプチャID
            detected_item_id: 検出されたアイテムのID
            detected_category: 検出カテゴリ
            detected_embedding: 検出アイテムの埋め込みベクトル
            detected_description: 生成された説明文
            search_results: [(候補アイテム, 最終スコア, スコア内訳)]のリスト
            is_manual: 手動補正かどうか

        Returns:
            作成されたSearchLogエントリ

        """
        try:
            # 検索ログを作成
            search_log = SearchLog(
                capture_id=capture_id,
                detected_item_id=detected_item_id,
                detected_category=detected_category,
                detected_embedding=(
                    detected_embedding.tolist()
                    if isinstance(detected_embedding, np.ndarray)
                    else detected_embedding
                ),
                detected_description=detected_description,
                search_k=len(search_results),
                is_manual_correction=is_manual,
            )
            self.session.add(search_log)
            self.session.flush()  # IDを取得するため

            # 各検索結果を記録
            for rank, (candidate, final_score, score_breakdown) in enumerate(
                search_results, 1
            ):
                result_item = SearchResultItem(
                    search_log_id=search_log.id,
                    wardrobe_item_id=candidate.get("item_id") or candidate.get("id"),
                    rank=rank,
                    embedding_similarity=score_breakdown.get(
                        "embedding_similarity", 0.0
                    ),
                    color_histogram_distance=score_breakdown.get(
                        "color_histogram_distance"
                    ),
                    texture_similarity=score_breakdown.get("texture_similarity"),
                    co_occurrence_score=score_breakdown.get("co_occurrence_score"),
                    final_score=final_score,
                )
                self.session.add(result_item)

            self.session.commit()
            logger.info(
                f"Logged search results: {search_log.id} with {len(search_results)} candidates"
            )

            return search_log

        except Exception as e:
            self.session.rollback()
            logger.error(f"Error logging search results: {e}")
            raise

    def update_feedback(
        self,
        search_log_id: str,
        correct_item_id: str,
        incorrect_item_ids: Optional[List[str]] = None,
    ):
        """検索結果にフィードバックを追加.

        Args:
            search_log_id: 検索ログID
            correct_item_id: 正解アイテムのID
            incorrect_item_ids: 不正解アイテムのIDリスト

        """
        try:
            # 検索結果アイテムを更新
            results = (
                self.session.query(SearchResultItem)
                .filter(SearchResultItem.search_log_id == search_log_id)
                .all()
            )

            for result in results:
                if result.wardrobe_item_id == correct_item_id:
                    result.is_correct = True
                    result.user_feedback = "correct"
                elif (
                    incorrect_item_ids and result.wardrobe_item_id in incorrect_item_ids
                ):
                    result.is_correct = False
                    result.user_feedback = "incorrect"

            self.session.commit()
            logger.info(f"Updated feedback for search log {search_log_id}")

        except Exception as e:
            self.session.rollback()
            logger.error(f"Error updating feedback: {e}")
            raise

    def get_hard_negatives(
        self, days_back: int = 7, min_similarity: float = 0.5, max_rank: int = 10
    ) -> List[Dict[str, Any]]:
        """ハードネガティブ（高類似度だが誤認）を抽出.

        Args:
            days_back: 何日前までのログを対象とするか
            min_similarity: 最小類似度閾値
            max_rank: 最大ランク（Top-K内）

        Returns:
            ハードネガティブのリスト

        """
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # ハードネガティブを検索
        hard_negatives = (
            self.session.query(SearchResultItem, SearchLog, ClothingItem)
            .join(SearchLog, SearchResultItem.search_log_id == SearchLog.id)
            .join(ClothingItem, SearchResultItem.wardrobe_item_id == ClothingItem.id)
            .filter(
                and_(
                    SearchLog.timestamp >= cutoff_date,
                    SearchResultItem.is_correct.is_(False),
                    SearchResultItem.embedding_similarity >= min_similarity,
                    SearchResultItem.rank <= max_rank,
                )
            )
            .all()
        )

        results = []
        for result_item, search_log, wardrobe_item in hard_negatives:
            results.append(
                {
                    "search_log_id": search_log.id,
                    "detected_item_id": search_log.detected_item_id,
                    "detected_category": search_log.detected_category,
                    "detected_embedding": search_log.detected_embedding,
                    "detected_description": search_log.detected_description,
                    "negative_item_id": wardrobe_item.id,
                    "negative_item_name": wardrobe_item.name,
                    "negative_item_category": wardrobe_item.category.value,
                    "negative_embedding": wardrobe_item.embedding_vector,
                    "similarity": result_item.embedding_similarity,
                    "rank": result_item.rank,
                    "timestamp": search_log.timestamp,
                }
            )

        logger.info(f"Found {len(results)} hard negatives")
        return results

    def get_search_statistics(self, days_back: int = 7) -> Dict[str, Any]:
        """検索統計を取得.

        Args:
            days_back: 何日前までのログを対象とするか

        Returns:
            統計情報

        """
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # 基本統計
        total_searches = (
            self.session.query(SearchLog)
            .filter(SearchLog.timestamp >= cutoff_date)
            .count()
        )

        # Top-1精度
        top1_correct = (
            self.session.query(SearchResultItem)
            .join(SearchLog, SearchResultItem.search_log_id == SearchLog.id)
            .filter(
                and_(
                    SearchLog.timestamp >= cutoff_date,
                    SearchResultItem.rank == 1,
                    SearchResultItem.is_correct.is_(True),
                )
            )
            .count()
        )

        # Top-5精度
        top5_searches = (
            self.session.query(SearchLog.id)
            .filter(SearchLog.timestamp >= cutoff_date)
            .subquery()
        )

        top5_correct = (
            self.session.query(
                func.count(func.distinct(SearchResultItem.search_log_id))
            )
            .filter(
                and_(
                    SearchResultItem.search_log_id.in_(top5_searches),
                    SearchResultItem.rank <= 5,
                    SearchResultItem.is_correct.is_(True),
                )
            )
            .scalar()
        )

        # カテゴリ別統計
        category_stats = (
            self.session.query(
                SearchLog.detected_category, func.count(SearchLog.id).label("count")
            )
            .filter(SearchLog.timestamp >= cutoff_date)
            .group_by(SearchLog.detected_category)
            .all()
        )

        return {
            "period_days": days_back,
            "total_searches": total_searches,
            "searches_with_feedback": self.session.query(SearchLog)
            .join(SearchResultItem, SearchResultItem.search_log_id == SearchLog.id)
            .filter(
                and_(
                    SearchLog.timestamp >= cutoff_date,
                    SearchResultItem.is_correct.isnot(None),
                )
            )
            .distinct()
            .count(),
            "top1_accuracy": (
                (top1_correct / total_searches) if total_searches > 0 else 0.0
            ),
            "top5_accuracy": (
                (top5_correct / total_searches) if total_searches > 0 else 0.0
            ),
            "category_distribution": {cat: count for cat, count in category_stats},
            "hard_negatives_count": len(self.get_hard_negatives(days_back)),
        }

    def cleanup_old_logs(self, days_to_keep: int = 30):
        """古いログを削除.

        Args:
            days_to_keep: 保持する日数

        """
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        try:
            deleted = (
                self.session.query(SearchLog)
                .filter(SearchLog.timestamp < cutoff_date)
                .delete()
            )

            self.session.commit()
            logger.info(f"Deleted {deleted} old search logs")

        except Exception as e:
            self.session.rollback()
            logger.error(f"Error cleaning up logs: {e}")
            raise
