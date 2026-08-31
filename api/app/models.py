"""Simplified database model for coordinate recorder
Single table design with logical deletion.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func

from .utils.timezone_utils import jst_now

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """Base model class."""

    pass


class Photo(Base):
    """Unified photo and outfit record table."""

    __tablename__ = "photos"

    # Primary key (use String for SQLite compatibility)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # File information
    filename = Column(String(255), unique=True, nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)  # Size in bytes
    resolution_width = Column(Integer, nullable=True)
    resolution_height = Column(Integer, nullable=True)

    # Capture information (JST統一)
    captured_at = Column(
        DateTime(timezone=True), nullable=False, default=jst_now, index=True
    )
    # 写真がどの経路で届いたか。'touchscreen'（タッチスクリーン UI）/
    # 'camera_retry'（Pi の再送ループ）/ 'upload'（手元の写真を手で上げる）。
    # 受け付ける値は app.routers.upload.UPLOAD_SOURCES が正典。
    # 別に 'test'（routers/misc.py のサンプル生成）と、語彙を決める前の古い行の
    # 値が入りうる
    source = Column(String(50), nullable=False)

    # Detection results
    person_detected = Column(Boolean, default=False, nullable=False, index=True)
    confidence_score = Column(Float, nullable=True)
    detection_count = Column(Integer, default=0, nullable=False)
    clothing_items = Column(JSON, nullable=True)  # ["シャツ", "ジーンズ", "スニーカー"]

    # AI Detection detailed results
    ai_detection_results = Column(JSON, nullable=True)  # 詳細なAI検出結果
    ai_detection_status = Column(
        String(20), default="pending"
    )  # pending, completed, failed
    ai_detection_error = Column(String(500), nullable=True)  # エラーメッセージ
    ai_cropped_images = Column(JSON, nullable=True)  # クロップされた画像のURL一覧

    # Processing metadata
    processing_time_ms = Column(Float, nullable=True)
    model_version = Column(String(50), nullable=True)

    # Weather context at capture date (設定地点の日次気温・Open-Meteo Archive で backfill)
    # 起床ブリーフ画面で「今日の気温に近い過去の記録」を照合するために使う
    temperature_max = Column(Float, nullable=True)
    temperature_min = Column(Float, nullable=True)

    # その日に会った人（カレンダー `@名前` 由来・撮影時に記録）。
    # 「前回その人と会った時のコーデ」を引くために使う。
    # 過去バックフィルはせず、デプロイ以降に撮影したぶんだけ貯まる。
    attendees = Column(JSON, nullable=True)  # ["太郎", "花子"]

    # Google Photos に上げたときの media item ID。
    # ⚠️ NULL は「未アップロード」を意味しない。この列は 2026-08-28 以降に付いたもので、
    # それ以前の成功分は遡って埋められない（記録がどこにも残っていない）。
    google_photos_media_item_id = Column(String(255), nullable=True)

    # Jina AI embedding fields
    embedding_vector = Column(JSON, nullable=True)  # Jina embedding as JSON array
    embedding_computed_at = Column(
        DateTime(timezone=True), nullable=True
    )  # When embedding was computed (JST統一)
    embedding_model_version = Column(
        String(50), nullable=True
    )  # Model version used (e.g., "jina-embeddings-v4")

    # Logical deletion (JST統一)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Timestamps (JST統一)
    created_at = Column(DateTime(timezone=True), default=jst_now)
    updated_at = Column(DateTime(timezone=True), default=jst_now, onupdate=jst_now)

    # Relationships
    outfit_records = relationship(
        "OutfitRecord",
        back_populates="photo",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index("idx_captured_at", "captured_at"),
        Index("idx_active_photos", "deleted_at", "captured_at"),
        Index("idx_person_detected", "person_detected", "deleted_at"),
    )


class OutfitRecord(Base):
    """Outfit records linking photos to clothing selections."""

    __tablename__ = "outfit_records"

    # Primary key (use String for SQLite compatibility)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Reference to photo
    photo_id = Column(
        String(36),
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Record metadata
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=jst_now)
    confidence_score = Column(Float, nullable=True)
    manual_selection = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=jst_now)
    updated_at = Column(DateTime(timezone=True), default=jst_now, onupdate=jst_now)

    # Relationships
    outfit_items = relationship(
        "OutfitItem", back_populates="outfit_record", cascade="all, delete-orphan"
    )
    external_rental_links = relationship(
        "OutfitExternalRentalItem",
        back_populates="outfit_record",
        cascade="all, delete-orphan",
    )
    photo = relationship(
        "Photo",
        back_populates="outfit_records",
        lazy="joined",
        passive_deletes=True,
    )

    # Indexes
    __table_args__ = (
        Index("idx_outfit_records_photo_id", "photo_id"),
        Index("idx_outfit_records_recorded_at", "recorded_at"),
    )


class OutfitItem(Base):
    """Individual clothing items in an outfit record."""

    __tablename__ = "outfit_items"

    # Primary key (use String for SQLite compatibility)
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Foreign keys (use String for SQLite compatibility)
    outfit_record_id = Column(
        String(36), ForeignKey("outfit_records.id", ondelete="CASCADE"), nullable=False
    )
    clothing_item_id = Column(
        String(36), ForeignKey("clothing_items.id", ondelete="CASCADE"), nullable=False
    )

    # Detection metadata
    detection_confidence = Column(Float, nullable=True)
    manual_added = Column(Boolean, default=True, nullable=False)

    # Position metadata (for future AI detection)
    position_x = Column(Integer, nullable=True)
    position_y = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    outfit_record = relationship("OutfitRecord", back_populates="outfit_items")
    clothing_item = relationship("ClothingItem")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "outfit_record_id", "clothing_item_id", name="uq_outfit_record_clothing"
        ),
        Index("idx_outfit_items_outfit_record_id", "outfit_record_id"),
        Index("idx_outfit_items_clothing_item_id", "clothing_item_id"),
    )


class OutfitExternalRentalItem(Base):
    """Link table between outfits and external rental items."""

    __tablename__ = "outfit_external_rental_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    outfit_record_id = Column(
        String(36), ForeignKey("outfit_records.id", ondelete="CASCADE"), nullable=False
    )
    external_rental_item_id = Column(
        String(36),
        ForeignKey("external_rental_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=jst_now)

    outfit_record = relationship("OutfitRecord", back_populates="external_rental_links")


class DetectionResult(Base):
    """AI detection results history table for Issue #451."""

    __tablename__ = "detection_results"

    # Primary key
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Foreign key to photo
    photo_id = Column(
        String(36),
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Detection metadata
    detection_type = Column(
        String(50), nullable=False
    )  # 'clothing', 'person', 'embedding'
    model_name = Column(
        String(100), nullable=False
    )  # 'roboflow_clothing_segmentation', 'jina-embeddings-v4'
    model_version = Column(String(50), nullable=True)

    # Results data
    detection_results = Column(JSON, nullable=True)  # Raw detection results
    confidence_score = Column(Float, nullable=True)  # Overall confidence
    processing_time_ms = Column(Float, nullable=True)  # Processing time

    # Embedding specific fields
    embedding_vector = Column(JSON, nullable=True)  # For embedding detections
    embedding_dimension = Column(Integer, nullable=True)  # Vector dimension

    # Status tracking
    status = Column(
        String(20), default="completed", nullable=False
    )  # completed, failed, partial
    error_message = Column(String(500), nullable=True)

    # Cache metadata
    cache_hit = Column(Boolean, default=False, nullable=False)  # Was this from cache?
    cache_key = Column(String(255), nullable=True, index=True)  # Cache identifier

    # Timestamps (JST統一)
    detected_at = Column(
        DateTime(timezone=True), nullable=False, default=jst_now, index=True
    )
    created_at = Column(DateTime(timezone=True), default=jst_now)

    # Relationships
    photo = relationship("Photo", backref="detection_history")

    # Indexes for performance
    __table_args__ = (
        Index("idx_detection_results_photo_type", "photo_id", "detection_type"),
        Index("idx_detection_results_detected_at", "detected_at"),
        Index("idx_detection_results_model", "model_name", "model_version"),
        Index("idx_detection_results_status", "status"),
    )


# View definition as SQL (to be created in database)
DAILY_SUMMARY_VIEW = """
CREATE OR REPLACE VIEW daily_summary AS
SELECT
    DATE(captured_at) as date,
    COUNT(*) FILTER (WHERE deleted_at IS NULL) as total_count,
    COUNT(*) FILTER (WHERE person_detected = true AND deleted_at IS NULL) as person_count,
    MAX(captured_at) FILTER (WHERE deleted_at IS NULL) as last_capture_time
FROM photos
GROUP BY DATE(captured_at)
ORDER BY date DESC;
"""
