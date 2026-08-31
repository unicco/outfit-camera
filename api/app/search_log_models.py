"""Models for search result logging and reranking."""

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator

from .database import Base


class JSONBCompatible(TypeDecorator):
    """JSON column using JSONB on PostgreSQL and JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":  # pragma: no cover - requires PostgreSQL
            from sqlalchemy.dialects.postgresql import JSONB

            return dialect.type_descriptor(JSONB(astext_type=Text()))
        return dialect.type_descriptor(JSON())


def json_column() -> JSONBCompatible:
    """Return a JSON-compatible column type for the current dialect."""
    return JSONBCompatible()


class SearchLog(Base):
    """検索ログ - 各検索クエリの記録."""

    __tablename__ = "search_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    capture_id = Column(String, nullable=True)  # AIキャプチャIDへの参照
    detected_item_id = Column(String, nullable=False)  # 検出されたアイテムのID
    detected_category = Column(String, nullable=False)  # 検出カテゴリ
    detected_embedding = Column(
        json_column(), nullable=True
    )  # 検出アイテムの埋め込みベクトル
    detected_description = Column(Text, nullable=True)  # 生成された説明文
    search_k = Column(Integer, nullable=False, default=20)  # Top-K パラメータ
    timestamp = Column(DateTime, nullable=False, server_default=func.now())
    is_manual_correction = Column(
        Boolean, nullable=False, default=False
    )  # 手動補正かどうか

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    search_results = relationship(
        "SearchResultItem", back_populates="search_log", cascade="all, delete-orphan"
    )


class SearchResultItem(Base):
    """検索結果アイテム - Top-K の各候補."""

    __tablename__ = "search_result_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    search_log_id = Column(String, ForeignKey("search_logs.id"), nullable=False)
    wardrobe_item_id = Column(String, ForeignKey("clothing_items.id"), nullable=False)

    # ランキング情報
    rank = Column(Integer, nullable=False)  # 1-based ranking

    # 各種スコア
    embedding_similarity = Column(Float, nullable=False)  # 埋め込み類似度
    color_histogram_distance = Column(Float, nullable=True)  # 色ヒストグラム距離
    texture_similarity = Column(Float, nullable=True)  # テクスチャ類似度
    co_occurrence_score = Column(Float, nullable=True)  # 共起確率スコア
    final_score = Column(Float, nullable=False)  # 最終スコア（再ランク後）

    # フィードバック
    is_correct = Column(Boolean, nullable=True)  # 正解かどうか（後から判明）
    user_feedback = Column(String, nullable=True)  # ユーザーフィードバック

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    search_log = relationship("SearchLog", back_populates="search_results")
    wardrobe_item = relationship("ClothingItem", lazy="joined")
