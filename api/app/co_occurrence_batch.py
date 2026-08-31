"""Batch job for updating co-occurrence data from outfit records."""

import logging
from datetime import date, datetime, timedelta
from typing import Dict

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from .co_occurrence_models import (
    CategoryCoOccurrence,
    CoOccurrenceLearningStat,
    DailyOutfitLog,
)
from .co_occurrence_service import CoOccurrenceService
from .models import OutfitItem, OutfitRecord, Photo
from .wardrobe_models import ClothingItem

logger = logging.getLogger(__name__)


class CoOccurrenceBatchProcessor:
    """共起データのバッチ処理プロセッサ."""

    def __init__(self, session: Session):
        self.session = session
        self.service = CoOccurrenceService(session)

    def process_daily_batch(
        self, target_date: date = None, days_back: int = 1
    ) -> CoOccurrenceLearningStat:
        """日次バッチ処理を実行.

        Args:
            target_date: 処理対象日（省略時は昨日）
            days_back: 何日前まで遡って処理するか

        Returns:
            処理統計

        """
        if not target_date:
            target_date = date.today() - timedelta(days=1)

        start_time = datetime.now()
        stats = {
            "records_processed": 0,
            "new_patterns_found": 0,
            "patterns_updated": 0,
            "item_pairs_processed": set(),
            "category_pairs_processed": set(),
        }

        try:
            # 指定期間のOutfitRecordを取得
            end_date = target_date
            start_date = target_date - timedelta(days=days_back - 1)

            outfit_records = (
                self.session.query(OutfitRecord)
                .join(Photo, OutfitRecord.photo_id == Photo.id)
                .filter(
                    and_(
                        func.date(Photo.captured_at) >= start_date,
                        func.date(Photo.captured_at) <= end_date,
                    )
                )
                .all()
            )

            logger.info(
                f"Processing {len(outfit_records)} outfit records from {start_date} to {end_date}"
            )

            # 各OutfitRecordを処理
            for record in outfit_records:
                self._process_outfit_record(record, stats)
                stats["records_processed"] += 1

            # カテゴリ別の確率を再計算
            self._recalculate_category_probabilities()

            # 処理時間を計算
            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            # 統計を記録
            learning_stat = CoOccurrenceLearningStat(
                batch_date=target_date,
                learning_type="daily_batch",
                records_processed=stats["records_processed"],
                new_patterns_found=stats["new_patterns_found"],
                patterns_updated=stats["patterns_updated"],
                processing_time_ms=processing_time,
                status="completed",
            )
            self.session.add(learning_stat)
            self.session.commit()

            logger.info(
                f"Daily batch completed: {stats['records_processed']} records, "
                f"{stats['new_patterns_found']} new patterns, "
                f"{stats['patterns_updated']} updated patterns"
            )

            return learning_stat

        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            self.session.rollback()

            # エラー統計を記録
            learning_stat = CoOccurrenceLearningStat(
                batch_date=target_date,
                learning_type="daily_batch",
                records_processed=stats.get("records_processed", 0),
                new_patterns_found=stats.get("new_patterns_found", 0),
                patterns_updated=stats.get("patterns_updated", 0),
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                status="failed",
                error_message=str(e),
            )
            self.session.add(learning_stat)
            self.session.commit()

            raise

    def _process_outfit_record(self, record: OutfitRecord, stats: Dict):
        """個別のOutfitRecordを処理."""
        # OutfitItemsを取得
        outfit_items = (
            self.session.query(OutfitItem)
            .filter(OutfitItem.outfit_record_id == record.id)
            .all()
        )

        if len(outfit_items) < 2:
            return

        # 着用アイテムIDを収集
        worn_item_ids = [item.clothing_item_id for item in outfit_items]

        # DailyOutfitLogが存在しない場合は作成
        capture_date = record.photo.captured_at.date()
        existing_log = (
            self.session.query(DailyOutfitLog)
            .filter(
                DailyOutfitLog.capture_date == capture_date,
                DailyOutfitLog.photo_id == record.photo_id,
            )
            .first()
        )

        if not existing_log:
            # 新規ログを作成
            self.service.record_outfit_wearing(
                photo_id=record.photo_id,
                worn_item_ids=worn_item_ids,
                capture_date=capture_date,
            )
            stats["new_patterns_found"] += 1
        else:
            # 既存のアイテムペア共起を更新
            worn_items = (
                self.session.query(ClothingItem)
                .filter(ClothingItem.id.in_(worn_item_ids))
                .all()
            )

            # アイテムペアを処理
            for i in range(len(worn_items)):
                for j in range(i + 1, len(worn_items)):
                    item1, item2 = worn_items[i], worn_items[j]
                    id1, id2 = sorted([item1.id, item2.id])
                    pair_key = (id1, id2)

                    if pair_key not in stats["item_pairs_processed"]:
                        stats["item_pairs_processed"].add(pair_key)
                        stats["patterns_updated"] += 1

    def _recalculate_category_probabilities(self):
        """カテゴリ別の確率を再計算."""
        # バッチサイズを設定してメモリ効率を向上
        batch_size = 1000
        offset = 0

        while True:
            # バッチ単位で取得
            category_records = (
                self.session.query(CategoryCoOccurrence)
                .offset(offset)
                .limit(batch_size)
                .all()
            )

            if not category_records:
                break

            # 事前に必要な統計情報をまとめて取得（N+1問題回避）
            category_pairs = set()
            for record in category_records:
                # 正規化されたペアを追加
                pair = tuple(sorted([record.category_1, record.category_2]))
                category_pairs.add(pair)

            # 統計情報を一括取得
            pair_totals = {}
            for cat1, cat2 in category_pairs:
                total = (
                    self.session.query(
                        func.sum(CategoryCoOccurrence.co_occurrence_count)
                    )
                    .filter(
                        CategoryCoOccurrence.category_1 == cat1,
                        CategoryCoOccurrence.category_2 == cat2,
                    )
                    .scalar()
                ) or 0
                pair_totals[(cat1, cat2)] = total

            # レコードを更新
            for record in category_records:
                pair = tuple(sorted([record.category_1, record.category_2]))
                total_occurrences = pair_totals.get(pair, 0)

                if total_occurrences > 0:
                    record.total_occurrences = total_occurrences
                    record.probability = record.co_occurrence_count / total_occurrences

            # バッチごとにコミット
            self.session.commit()
            offset += batch_size

            logger.info(f"Processed {offset} category co-occurrence records")

    def migrate_existing_data(self):
        """既存のOutfitRecordから共起データを移行."""
        logger.info("Starting migration of existing outfit data...")

        # 全OutfitRecordを取得
        all_records = self.session.query(OutfitRecord).all()
        total_records = len(all_records)

        logger.info(f"Found {total_records} outfit records to migrate")

        stats = {
            "records_processed": 0,
            "new_patterns_found": 0,
            "patterns_updated": 0,
            "item_pairs_processed": set(),
            "category_pairs_processed": set(),
        }

        # バッチ処理
        batch_size = 100
        for i in range(0, total_records, batch_size):
            batch = all_records[i : i + batch_size]

            for record in batch:
                self._process_outfit_record(record, stats)
                stats["records_processed"] += 1

            # 定期的にコミット
            self.session.commit()
            logger.info(
                f"Processed {stats['records_processed']}/{total_records} records"
            )

        # 最終的な確率を再計算
        self._recalculate_category_probabilities()

        logger.info(
            f"Migration completed: {stats['records_processed']} records, "
            f"{stats['new_patterns_found']} new patterns, "
            f"{stats['patterns_updated']} updated patterns"
        )

    def cleanup_old_data(self, days_to_keep: int = 90):
        """古い学習統計データをクリーンアップ."""
        cutoff_date = date.today() - timedelta(days=days_to_keep)

        deleted = (
            self.session.query(CoOccurrenceLearningStat)
            .filter(CoOccurrenceLearningStat.batch_date < cutoff_date)
            .delete()
        )

        self.session.commit()
        logger.info(f"Cleaned up {deleted} old learning stat records")
