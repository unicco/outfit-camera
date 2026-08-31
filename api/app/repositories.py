"""Simplified repository for single-table design."""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from .models import Photo
from .utils.timezone_utils import TimezoneUtils


class PhotoRepository:
    """Repository for photo management with outfit records."""

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        filename: str,
        file_path: str,
        source: str,
        captured_at: datetime | None = None,
        file_size: int | None = None,
        resolution_width: int | None = None,
        resolution_height: int | None = None,
        person_detected: bool = False,
        confidence_score: float | None = None,
        detection_count: int = 0,
        clothing_items: list[str] | None = None,
        processing_time_ms: float | None = None,
        model_version: str | None = None,
        photo_id: str | None = None,
        attendees: list[str] | None = None,
    ) -> Photo:
        """Create new photo record with outfit information."""
        photo = Photo(
            id=photo_id if photo_id else str(uuid.uuid4()),
            filename=filename,
            file_path=file_path,
            attendees=attendees or None,
            file_size=file_size,
            resolution_width=resolution_width,
            resolution_height=resolution_height,
            captured_at=(
                captured_at
                if captured_at is not None
                else TimezoneUtils.now_jst_naive()
            ),
            source=source,
            person_detected=person_detected,
            confidence_score=confidence_score,
            detection_count=detection_count,
            clothing_items=clothing_items or [],
            processing_time_ms=processing_time_ms,
            model_version=model_version,
        )

        self.db.add(photo)
        self.db.commit()
        self.db.refresh(photo)
        return photo

    def get_by_id(self, photo_id: UUID | str) -> Photo | None:
        """Get active photo by ID."""
        # Convert UUID to string since id is stored as String(36) in database
        photo_id_str = str(photo_id)
        return (
            self.db.query(Photo)
            .filter(Photo.id == photo_id_str, Photo.deleted_at.is_(None))
            .first()
        )

    def get_by_id_including_deleted(self, photo_id: UUID | str) -> Photo | None:
        """Get photo by ID regardless of soft deletion.

        アップロードの冪等判定に使う。`get_by_id` は削除済を見ないため、削除済の
        photo_id を「無い」と判断して INSERT すると PK 衝突で 409 になり、Pi の再送が
        永久に失敗し続ける。
        """
        return self.db.query(Photo).filter(Photo.id == str(photo_id)).first()

    def update(self, photo_id: UUID | str, **kwargs: Any) -> Photo | None:
        """Update photo record."""
        photo = self.get_by_id(photo_id)
        if photo:
            for key, value in kwargs.items():
                if hasattr(photo, key):
                    setattr(photo, key, value)
            self.db.commit()
            self.db.refresh(photo)
            return photo
        return None

    def get_recent(
        self, limit: int = 50, include_no_person: bool = True
    ) -> list[Photo]:
        """Get recent active photos."""
        query = self.db.query(Photo).filter(Photo.deleted_at.is_(None))

        if not include_no_person:
            query = query.filter(Photo.person_detected.is_(True))

        return query.order_by(desc(Photo.captured_at)).limit(limit).all()

    def get_by_date(self, target_date: date) -> list[Photo]:
        """Get all active photos for a specific date."""
        from datetime import timezone as dt_timezone

        # Convert to timezone-aware datetimes (UTC) for database comparison
        start = datetime.combine(target_date, datetime.min.time()).replace(
            tzinfo=dt_timezone.utc
        )
        end = datetime.combine(target_date, datetime.max.time()).replace(
            tzinfo=dt_timezone.utc
        )

        return (
            self.db.query(Photo)
            .filter(
                and_(
                    Photo.captured_at >= start,
                    Photo.captured_at <= end,
                    Photo.deleted_at.is_(None),
                )
            )
            .order_by(desc(Photo.captured_at))
            .all()
        )

    def get_by_date_range(
        self, start_date: datetime, end_date: datetime, limit: int = 1000
    ) -> list[Photo]:
        """Get active photos within date range with optional limit."""
        return (
            self.db.query(Photo)
            .filter(
                and_(
                    Photo.captured_at >= start_date,
                    Photo.captured_at <= end_date,
                    Photo.deleted_at.is_(None),
                )
            )
            .order_by(desc(Photo.captured_at))
            .limit(limit)
            .all()
        )

    def soft_delete(self, photo_id: UUID) -> bool:
        """Soft delete photo by ID."""
        photo = self.get_by_id(photo_id)
        if photo:
            photo.deleted_at = datetime.now(timezone.utc)  # type: ignore[assignment]
            self.db.commit()
            return True
        return False

    def delete_no_person_photos(self) -> int:
        """Soft delete all photos where no person was detected."""
        updated = (
            self.db.query(Photo)
            .filter(and_(Photo.person_detected.is_(False), Photo.deleted_at.is_(None)))
            .update({"deleted_at": TimezoneUtils.now_jst_naive()})
        )
        self.db.commit()
        return updated

    def get_daily_summary(self, days: int = 7) -> list[dict[str, Any]]:
        """Get daily capture summary for recent days."""
        cutoff_date = TimezoneUtils.now_jst_naive() - timedelta(days=days)

        result = (
            self.db.query(
                func.date(Photo.captured_at).label("date"),
                func.count(Photo.id).label("total_count"),
                func.count(Photo.id)
                .filter(Photo.person_detected.is_(True))
                .label("person_count"),
                func.max(Photo.captured_at).label("last_capture"),
            )
            .filter(and_(Photo.captured_at >= cutoff_date, Photo.deleted_at.is_(None)))
            .group_by(func.date(Photo.captured_at))
            .order_by(desc(func.date(Photo.captured_at)))
            .all()
        )

        return [
            {
                "date": (
                    row.date.isoformat()
                    if hasattr(row.date, "isoformat")
                    else str(row.date)
                ),
                "total_count": row.total_count,
                "person_count": row.person_count or 0,
                "captured": row.total_count > 0,
                "last_capture": (
                    row.last_capture.isoformat()
                    if row.last_capture and hasattr(row.last_capture, "isoformat")
                    else str(row.last_capture) if row.last_capture else None
                ),
            }
            for row in result
        ]

    def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics for active photos."""
        stats = (
            self.db.query(
                func.count(Photo.id).label("total_photos"),
                func.sum(Photo.file_size).label("total_size"),
                func.avg(Photo.file_size).label("avg_size"),
                func.count(Photo.id)
                .filter(Photo.person_detected.is_(True))
                .label("person_photos"),
            )
            .filter(Photo.deleted_at.is_(None))
            .first()
        )

        return {
            "total_photos": stats.total_photos or 0,
            "total_size_bytes": stats.total_size or 0,
            "average_size_bytes": int(stats.avg_size or 0),
            "person_detected_count": stats.person_photos or 0,
        }

    def cleanup_old_photos(self, keep_days: int = 30) -> int:
        """Soft delete photos older than specified days."""
        cutoff_date = TimezoneUtils.now_jst_naive() - timedelta(days=keep_days)

        updated = (
            self.db.query(Photo)
            .filter(and_(Photo.captured_at < cutoff_date, Photo.deleted_at.is_(None)))
            .update({"deleted_at": TimezoneUtils.now_jst_naive()})
        )
        self.db.commit()
        return updated

    def get_all_with_embeddings(self) -> list[Photo]:
        """Get all photos that have embedding vectors."""
        return (
            self.db.query(Photo)
            .filter(
                and_(Photo.deleted_at.is_(None), Photo.embedding_vector.is_not(None))
            )
            .order_by(desc(Photo.captured_at))
            .all()
        )
