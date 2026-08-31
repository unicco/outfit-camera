"""写真関連のエンドポイント."""

import asyncio
import logging
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..api_shared import DATABASE_MODE, get_emergency_photos_response
from ..schemas.api_v2 import PhotoResponse as ApiPhotoResponse
from ..services.ai_detection_service import (
    AI_DETECTION_THREAD_POOL,
    run_ai_detection_with_new_session,
)
from ..settings import get_settings
from ..storage.storage_factory import get_google_photos_handler, get_storage_handler
from ..schemas.base import BaseModel
from ..utils.timezone_utils import TimezoneUtils

# データベース関連のインポート（optional）
try:
    from ..database import get_db
    from ..repositories import PhotoRepository

    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    get_db = None
    PhotoRepository = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["photos"])

# Google Photos アップロード用のスレッドプール
GOOGLE_PHOTOS_THREAD_POOL = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="google_photos"
)


def upload_to_google_photos_background(
    photo_uuid: str, photo_url: str, description: str, timestamp: datetime
):
    """Google Photos へのアップロードをバックグラウンドで実行."""
    try:
        google_photos_handler = get_google_photos_handler()
        if not google_photos_handler.is_authenticated():
            logger.info("Google Photos not authenticated, skipping upload")
            return

        logger.info(f"Starting Google Photos upload for photo {photo_uuid}")

        # 写真をダウンロードして Google Photos にアップロード
        media_item_id = google_photos_handler.upload_photo_from_url(
            photo_url, description
        )

        if media_item_id:
            logger.info(
                f"Successfully uploaded photo {photo_uuid} to Google Photos: {media_item_id}"
            )

            # データベースに保存（利用可能な場合）
            if DB_AVAILABLE:
                try:
                    from ..database import SessionLocal

                    with SessionLocal() as db:
                        photo_repo = PhotoRepository(db)
                        photo = photo_repo.find_by_id(photo_uuid)
                        if photo:
                            photo.google_photos_media_item_id = media_item_id
                            db.commit()
                            logger.info(
                                f"Saved Google Photos media item ID to database for photo {photo_uuid}"
                            )
                except Exception as db_error:
                    logger.error(
                        f"Failed to save Google Photos media item ID to database: {db_error}"
                    )
        else:
            logger.warning(f"Failed to upload photo {photo_uuid} to Google Photos")

    except Exception as e:
        logger.error(f"Error in background Google Photos upload for {photo_uuid}: {e}")


class PhotoRequest(BaseModel):
    """写真保存リクエストモデル."""

    filename: str


class PhotoResponse(BaseModel):
    """写真保存レスポンスモデル."""

    status: str
    record_id: str
    photo_id: str
    message: str
    source_path: str
    destination_path: str
    file_exists: bool


@router.post("/photos", response_model=PhotoResponse)
async def save_photo(request: PhotoRequest) -> PhotoResponse:
    """TouchScreen撮影後の写真保存エンドポイント."""
    filename = request.filename
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    try:
        # Extract actual filename from URL
        if filename.startswith("http"):
            actual_filename = filename.split("/")[-1]
        else:
            actual_filename = filename

        # Generate UUID for the photo
        photo_uuid = str(uuid.uuid4())
        storage_handler = get_storage_handler()
        settings = get_settings()

        # Dynamic path resolution for camera photos directory
        camera_photos_dir = os.path.expanduser(
            os.getenv(
                "CAMERA_PHOTOS_DIR", str(settings.project_root / "camera" / "photos")
            )
        )
        source_path = os.path.join(camera_photos_dir, actual_filename)
        destination_path = os.path.join(settings.photos_dir, f"{photo_uuid}.jpg")

        if os.path.exists(source_path):
            shutil.copy2(source_path, destination_path)
            logger.info(f"Copied photo from {source_path} to {destination_path}")

            # Metadata should be saved to database, not memory storage
            timestamp = datetime.now()
            logger.info(
                f"Photo {photo_uuid} saved for TouchScreen capture at {timestamp}"
            )

            # Use unified storage handler for file URL generation
            file_url = storage_handler.get_file_url(photo_uuid)
            logger.info(
                f"Generated storage URL for TouchScreen photo {photo_uuid}: {file_url}"
            )

            # Google Photos へのアップロードをバックグラウンドスレッドで実行
            photo_url = f"{settings.api_url}/photos/{photo_uuid}"
            description = f"全身写真 - {timestamp.strftime('%Y年%m月%d日 %H:%M')}"

            # ThreadPoolExecutor で非同期実行
            future = GOOGLE_PHOTOS_THREAD_POOL.submit(
                upload_to_google_photos_background,
                photo_uuid,
                photo_url,
                description,
                timestamp,
            )

            # エラーハンドリングのためのコールバック
            def handle_upload_error(future):
                try:
                    future.result()
                except Exception as e:
                    logger.error(
                        f"Background Google Photos upload failed for {photo_uuid}: {e}"
                    )

            future.add_done_callback(handle_upload_error)

        else:
            logger.warning(f"Source photo not found: {source_path}")
            photo_uuid = actual_filename  # Fallback to original filename

        # Save to outfit records for history
        record_id = str(uuid.uuid4())

        logger.info(f"Photo saved via TouchScreen: {filename} -> {photo_uuid}")
        return PhotoResponse(
            status="success",
            record_id=record_id,
            photo_id=photo_uuid,
            message="Photo saved successfully from TouchScreen",
            source_path=source_path,
            destination_path=destination_path,
            file_exists=os.path.exists(destination_path),
        )

    except Exception as e:
        logger.error(f"Failed to save photo {filename}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save photo")


@router.get("/photos/{photo_id}")
async def get_photo_binary(photo_id: str) -> Response:
    """写真バイナリデータ取得エンドポイント（履歴画面の写真表示用）."""
    try:
        storage_handler = get_storage_handler()
        clean_photo_id = storage_handler.validate_photo_id(photo_id)
        settings = get_settings()

        # GCS モードでは BaseStorageHandler が返す公開 URL へリダイレクトする
        if settings.storage_type == "gcs":
            photo_url = storage_handler.get_photo_url(clean_photo_id)
            logger.info(f"Redirecting to GCS photo URL: {photo_url}")
            return RedirectResponse(
                url=photo_url,
                status_code=302,
                headers={
                    "Cache-Control": "public, max-age=86400, immutable",
                    "X-Storage-Type": "gcs",
                },
            )

        else:
            # Local file mode
            # Try with .jpg extension first
            photo_path = Path(settings.photos_dir) / f"{clean_photo_id}.jpg"

            if not photo_path.exists():
                # Try without extension
                photo_path = Path(settings.photos_dir) / clean_photo_id
                if not photo_path.exists():
                    # Try as-is (if extension was included)
                    photo_path = Path(settings.photos_dir) / photo_id
                    if not photo_path.exists():
                        raise HTTPException(
                            status_code=404, detail=f"Photo not found: {photo_id}"
                        )

            logger.info(f"Serving photo: {photo_path}")
            return FileResponse(
                path=str(photo_path),
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "public, max-age=86400, immutable",
                    "X-Storage-Type": "local",
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get photo {photo_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get photo")


@router.post("/photos/{photo_id}/capture", response_model=None)
async def mark_photo_captured(
    photo_id: UUID, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """Mark photo as captured (compatibility endpoint)."""
    repo = PhotoRepository(db)
    photo = repo.get_by_id(photo_id)

    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    return {"success": True, "message": "Photo marked as captured"}


@router.delete("/photos/no-person", response_model=None)
async def delete_no_person_photos(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Delete all photos where no person was detected."""
    repo = PhotoRepository(db)
    deleted_count = repo.delete_no_person_photos()

    return {
        "success": True,
        "message": f"{deleted_count}件の「人物なし」記録を削除しました",
        "deleted_count": deleted_count,
    }


@router.get("/photo/{photo_id}", response_model=None)
async def get_photo(photo_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get photo data by ID (base64 encoded)."""
    try:
        # Try to parse as UUID
        try:
            photo_uuid = UUID(photo_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid photo ID format")

        repo = PhotoRepository(db)
        photo = repo.get_by_id(photo_uuid)

        if not photo:
            raise HTTPException(status_code=404, detail="Photo not found")

        # For API compatibility, we return a simple structure
        # In a real implementation, you'd read the file and encode it
        return {
            "photo_id": str(photo.id),
            "image_data": f"base64_encoded_image_data_for_{photo.filename}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get photo: {e}")
        raise HTTPException(status_code=500, detail="Failed to get photo") from e


@router.get("/photos/{photo_id}/metadata", response_model=None)
async def get_photo_metadata(
    photo_id: str, db: Session | None = Depends(get_db) if DB_AVAILABLE else None
) -> dict[str, Any]:
    """Get photo metadata including AI detection results."""
    if not DB_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        repo = PhotoRepository(db)
        # photo_id can be either UUID or camera format (photo_YYYYMMDD_HHMMSS)
        photo = repo.get_by_id(photo_id)

        if not photo:
            raise HTTPException(status_code=404, detail="Photo not found")

        # Build response with AI detection details
        response = {
            "id": str(photo.id),
            "filename": photo.filename,
            "captured_at": photo.captured_at.isoformat() if photo.captured_at else None,
            "person_detected": photo.person_detected,
            "confidence_score": photo.confidence_score,
            "ai_detection_status": getattr(photo, "ai_detection_status", None),
            "ai_detection_results": getattr(photo, "ai_detection_results", None),
            "ai_detection_error": getattr(photo, "ai_detection_error", None),
            "ai_cropped_images": getattr(photo, "ai_cropped_images", None),
            "photo_url": (
                str(photo.file_path) if photo.file_path else None
            ),  # GCS URL を追加
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get photo metadata: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get photo metadata"
        ) from e


# NOTE: api.py の `PhotoResponse`（写真表現モデル）を ApiPhotoResponse として使う。
# この router 冒頭で定義済の PhotoResponse（保存レスポンス）とは別物のため別名で衝突回避。
# クラスの __name__ は "PhotoResponse" のままなので OpenAPI コンポーネント名は不変。
@router.get("/photos", response_model=list[ApiPhotoResponse])
async def get_photos(
    limit: int = 50,
    date_filter: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session | None = Depends(get_db),
) -> list[ApiPhotoResponse]:
    """Get recent photos with optional date filtering."""
    # Handle DATABASE_MODE settings
    if DATABASE_MODE == "required":
        if not DB_AVAILABLE or db is None:
            raise HTTPException(
                status_code=503, detail="Database required but unavailable"
            )
    elif DATABASE_MODE == "fileonly":
        # Minimal file-only fallback (simplified for Issue #237)
        return get_emergency_photos_response()
    elif not DB_AVAILABLE or db is None:
        # Simplified fallback for DATABASE_MODE=fallback
        return get_emergency_photos_response()

    repo = PhotoRepository(db)

    if start_date and end_date:
        # Date range filtering for calendar view (JST統一)
        start_datetime, _ = TimezoneUtils.get_jst_date_range(start_date)
        _, end_datetime = TimezoneUtils.get_jst_date_range(end_date)
        photos = repo.get_by_date_range(start_datetime, end_datetime, limit=limit)
    elif date_filter:
        # Single date filtering (JST統一)
        start_datetime, end_datetime = TimezoneUtils.get_jst_date_range(date_filter)
        photos = repo.get_by_date_range(start_datetime, end_datetime)
    else:
        # Recent photos
        photos = repo.get_recent(limit=limit)

    return [
        ApiPhotoResponse(
            id=str(photo.id),
            filename=str(photo.filename),
            captured_at=photo.captured_at,  # type: ignore[arg-type]
            person_detected=bool(photo.person_detected),
            confidence_score=(
                float(photo.confidence_score)
                if photo.confidence_score is not None
                else None
            ),
            clothing_items=list(photo.clothing_items) if photo.clothing_items else [],
            source=str(photo.source),
            ai_detection_status=getattr(photo, "ai_detection_status", None),
            ai_detection_results=getattr(photo, "ai_detection_results", None),
            photo_url=(
                str(photo.file_path) if photo.file_path else None
            ),  # GCS URL を追加
        )
        for photo in photos
    ]


@router.post("/photos/{photo_id}/ai-detection/reprocess", response_model=None)
async def reprocess_photo_ai_detection(
    photo_id: str, db: Session | None = Depends(get_db) if DB_AVAILABLE else None
) -> dict[str, Any]:
    """Re-run AI detection for a photo and persist results."""
    if not DB_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        repo = PhotoRepository(db)
        photo = repo.get_by_id(photo_id)

        if not photo:
            raise HTTPException(status_code=404, detail="Photo not found")

        try:
            repo.update(
                str(photo.id),
                ai_detection_status="pending",
                ai_detection_error=None,
                ai_detection_results=None,
                ai_cropped_images=None,
                detection_count=0,
                person_detected=False,
            )
        except Exception as update_error:
            logger.error(
                f"Failed to reset AI detection status for photo {photo_id}: {update_error}"
            )
            raise

        def run_ai_detection_sync() -> None:
            """同期実行用のラッパー関数."""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(run_ai_detection_with_new_session(photo_id))
                finally:
                    loop.close()
            except Exception as exc:
                logger.error(f"Background AI detection failed: {exc}")
                raise

        future = AI_DETECTION_THREAD_POOL.submit(run_ai_detection_sync)

        def handle_ai_detection_result(future: Any) -> None:
            try:
                future.result()
                logger.info(
                    f"✅ Background AI detection completed for photo {photo_id}"
                )
            except Exception as exc:
                logger.error(
                    f"❌ Background AI detection failed for photo {photo_id}: {exc}"
                )

        future.add_done_callback(handle_ai_detection_result)
        logger.info(f"✅ AI detection reprocess queued for photo {photo_id}")

        return {
            "photo_id": str(photo.id),
            "status": "queued",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reprocess AI detection: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to reprocess AI detection"
        ) from e
