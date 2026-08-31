"""Co-occurrence tracking database models for outfit learning."""

import uuid

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from .models import Base


class ItemPairCoOccurrence(Base):
    """具体的なアイテムペアの共起頻度を追跡."""

    __tablename__ = "item_pair_co_occurrences"
    __table_args__ = (
        UniqueConstraint("item_id_1", "item_id_2", name="pk_item_pair_co_occurrences"),
        Index("idx_item_pair_co_occur_count", "co_occurrence_count"),
        Index("idx_item_pair_last_worn", "last_worn_date"),
        Index("idx_item_pair_item2", "item_id_2"),
        {"comment": "具体的なアイテムペアの共起頻度を追跡"},
    )

    item_id_1 = Column(
        String(36),
        ForeignKey("clothing_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    item_id_2 = Column(
        String(36),
        ForeignKey("clothing_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    co_occurrence_count = Column(Integer, nullable=False, server_default="0")
    last_worn_date = Column(Date, nullable=True)
    confidence_score = Column(
        Float, nullable=True, comment="組み合わせの信頼度スコア (0-1)"
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def normalize_pair(self, item1: str, item2: str) -> tuple[str, str]:
        """アイテムペアを正規化（順序を統一）."""
        return (min(item1, item2), max(item1, item2))


class CategoryCoOccurrence(Base):
    """カテゴリレベルの共起パターンを追跡."""

    __tablename__ = "category_co_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "category_1",
            "category_2",
            "subcategory_1",
            "subcategory_2",
            "season",
            name="pk_category_co_occurrences",
        ),
        Index("idx_category_co_occur_prob", "probability"),
        Index("idx_category_co_occur_season", "season"),
        {"comment": "カテゴリレベルの共起パターンを追跡"},
    )

    category_1 = Column(String(50), primary_key=True)
    category_2 = Column(String(50), primary_key=True)
    subcategory_1 = Column(
        String(50), primary_key=True, nullable=True, server_default=""
    )
    subcategory_2 = Column(
        String(50), primary_key=True, nullable=True, server_default=""
    )
    season = Column(
        String(20),
        primary_key=True,
        nullable=True,
        server_default="",
        comment="季節別の統計（spring, summer, autumn, winter）",
    )
    co_occurrence_count = Column(Integer, nullable=False, server_default="0")
    total_occurrences = Column(Integer, nullable=False, server_default="0")
    probability = Column(Float, nullable=False, server_default="0.0")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DailyOutfitLog(Base):
    """日次の着用記録から学習データを生成."""

    __tablename__ = "daily_outfit_logs"
    __table_args__ = (
        UniqueConstraint("capture_date", "photo_id", name="uq_daily_outfit_date_photo"),
        Index("idx_daily_outfit_date", "capture_date"),
        Index("idx_daily_outfit_photo", "photo_id"),
        {"comment": "日次の着用記録から学習データを生成"},
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    capture_date = Column(Date, nullable=False)
    photo_id = Column(
        String(36), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True
    )
    worn_item_ids = Column(JSON, nullable=False, comment="着用アイテムIDのリスト")
    worn_categories = Column(JSON, nullable=False, comment="着用カテゴリの集計")
    weather_info = Column(JSON, nullable=True, comment="天気情報（将来の拡張用）")
    occasion = Column(
        String(50), nullable=True, comment="着用シーン（casual, business, formal等）"
    )
    user_rating = Column(Integer, nullable=True, comment="ユーザーの満足度評価（1-5）")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CoOccurrenceLearningStat(Base):
    """共起学習のバッチ処理履歴."""

    __tablename__ = "co_occurrence_learning_stats"
    __table_args__ = (
        Index("idx_learning_stats_date", "batch_date"),
        Index("idx_learning_stats_type", "learning_type"),
        {"comment": "共起学習のバッチ処理履歴"},
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_date = Column(Date, nullable=False)
    learning_type = Column(String(20), nullable=False, comment="item_pair, category")
    records_processed = Column(Integer, nullable=False)
    new_patterns_found = Column(Integer, nullable=False)
    patterns_updated = Column(Integer, nullable=False)
    processing_time_ms = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, server_default="completed")
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
