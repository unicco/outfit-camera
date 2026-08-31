"""写真アップロード・処理エンドポイント.

api.py モノリス（削除済）から verbatim 移動。共有ヘルパー（get_db / DB_AVAILABLE /
PhotoRepository / Photo / _record_today_attendees）は恒久 home の ..api_shared から
import する。
"""

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..api_shared import (
    DB_AVAILABLE,
    Photo,
    PhotoRepository,
    _record_today_attendees,
    get_db,
)
from ..services.ai_detection_service import (
    AI_DETECTION_THREAD_POOL,
    run_ai_detection_with_new_session,
)
from ..upload_limits import MAX_IMAGE_UPLOAD_BYTES, read_upload_capped
from ..utils.timezone_utils import TimezoneUtils, jst_now

try:
    from coordinate_recorder.logging_utils import log_with_context
except ImportError:  # pragma: no cover - fallback when module unavailable

    def log_with_context(*args: Any, **kwargs: Any) -> None:
        """Fallback logger when coordinate_recorder logging utils are absent."""
        return None


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["upload"])

# 写真がどの経路で届いたか（Photo.source）。送り手は 3 つあり、それぞれ別の値を送る。
# 列挙で縛るのは、クライアントの投げた任意の文字列がそのまま列に入るのを避けるため
UPLOAD_SOURCES = frozenset({"touchscreen", "camera_retry", "upload"})
DEFAULT_UPLOAD_SOURCE = "upload"


def record_attendees_background(photo_id_str: str) -> None:
    """その日に会った人を写真へ後から記録する.

    ICS フィードの取得は 1 本あたり数秒かかるため、アップロード応答のクリティカル
    パスには乗せない。AI 検出・Google Photos と同じくレコード作成後に実行する。
    参加者が取れない・DB 更新に失敗しても写真の保存は成立させる（best-effort）。
    """
    try:
        attendees = _record_today_attendees()
        if not attendees or not DB_AVAILABLE:
            return

        from ..database import SessionLocal

        with SessionLocal() as new_db:
            photo_record = new_db.query(Photo).filter(Photo.id == photo_id_str).first()
            if photo_record:
                photo_record.attendees = attendees
                new_db.commit()
                # 名前は PII なので件数だけログする
                logger.info(
                    f"Recorded {len(attendees)} attendees for photo {photo_id_str}"
                )
    except Exception as exc:
        logger.error(f"Failed to record attendees for photo {photo_id_str}: {exc}")


def upload_to_google_photos_background(
    photo_id_str: str, file_contents: bytes, timestamp: datetime
) -> str:
    """Google Photos へのバックグラウンドアップロード.

    Returns:
        ``"uploaded"`` / ``"unauthenticated"`` / ``"failed"`` / ``"error"``。
        完了コールバックがこの値でログの成否を決めるため、例外で抜けずに必ず返す。
    """
    try:
        from ..storage.storage_factory import get_google_photos_handler

        google_photos_handler = get_google_photos_handler()
        if google_photos_handler and google_photos_handler.is_authenticated():
            logger.info(f"Uploading photo {photo_id_str} to Google Photos")

            # 一時ファイルに保存してアップロード
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_file.write(file_contents)
                temp_file_path = temp_file.name

            try:
                description = f"全身写真 - {timestamp.strftime('%Y年%m月%d日 %H:%M')}"
                media_item_id = google_photos_handler.upload_photo(
                    temp_file_path, description
                )

                if media_item_id and DB_AVAILABLE:
                    # データベースに google_photos_media_item_id を保存（新しいセッションを作成）
                    try:
                        from ..database import SessionLocal

                        with SessionLocal() as new_db:
                            photo_record = (
                                new_db.query(Photo)
                                .filter(Photo.id == photo_id_str)
                                .first()
                            )
                            if photo_record:
                                photo_record.google_photos_media_item_id = media_item_id
                                new_db.commit()
                                logger.info(
                                    f"Saved Google Photos media item ID to database: {media_item_id}"
                                )
                    except Exception as db_error:
                        logger.error(
                            f"Failed to save Google Photos media item ID: {db_error}"
                        )

                if media_item_id:
                    logger.info(
                        f"Successfully uploaded photo {photo_id_str} to Google Photos: {media_item_id}"
                    )
                    return "uploaded"
                logger.warning(
                    f"Failed to upload photo {photo_id_str} to Google Photos"
                )
                return "failed"
            finally:
                # 一時ファイルを削除。finally 内で例外が出ると return 値が捨てられて
                # 外側の except に落ちるため、後片付けの失敗で upload の結果を
                # 上書きしないよう握り潰す（成功が "error" に化ける）。
                try:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                except OSError as cleanup_error:
                    logger.warning(
                        f"Failed to remove temp file {temp_file_path}: {cleanup_error}"
                    )
        else:
            # GOOGLE_PHOTOS_ENABLED を読む実装はどこにも無く「設定で止めている」
            # 状態が存在しないので、未認証は常に異常として扱ってよい。
            logger.error(
                f"Google Photos not authenticated, skipping upload for photo {photo_id_str}"
            )
            return "unauthenticated"
    except Exception as e:
        logger.error(f"Error uploading to Google Photos: {e}")
        # Google Photos へのアップロードエラーは写真保存の失敗とはしない
        return "error"


def log_google_photos_upload_result(photo_id_str: str, result: Any) -> None:
    """バックグラウンド upload の結果をログに落とす.

    ``"uploaded"`` 以外は未知の値も含めてすべて ERROR に落とす（fail-safe の向き）。
    """
    if result == "uploaded":
        logger.info(
            f"✅ Background Google Photos upload completed for photo {photo_id_str}"
        )
    else:
        logger.error(
            f"❌ Background Google Photos upload did not store photo {photo_id_str} "
            f"(result={result})"
        )


def _resolve_source(source: str | None) -> str:
    """Form の source を Photo.source に入れてよい値へ丸める.

    知らない値でも 400 にはしない。写真は撮り直しの効かない一度きりの記録なので、
    経路のラベルが読めないという理由で保存ごと失わせない。
    """
    if source is None:
        return DEFAULT_UPLOAD_SOURCE
    if source not in UPLOAD_SOURCES:
        # ここに来る値だけは allowlist を通っていない＝改行も長さも制限が無い。
        # repr で改行を殺し、長さを切ってからログに出す
        logger.warning(
            f"Unknown upload source {source[:50]!r}; "
            f"recording as '{DEFAULT_UPLOAD_SOURCE}'"
        )
        return DEFAULT_UPLOAD_SOURCE
    return source


def _duplicate_response(existing: Photo, original_name: str) -> dict[str, Any]:
    """既に受け付け済の photo_id に対する応答を組み立てる.

    削除済でも新しいレコードは作らない。作ると、人が消した写真が別 ID で蘇る。
    Pi の再送は 200 を成功とみなして未送信マークを消すので、これで収束する
    （409 を返すと届く見込みのない再送が 5 分ごとに続く）。

    2 回目以降が名乗った source は捨てる。`Photo.source` は「最初に書き込みに
    成功した経路」で確定させる（他のフィールドも同じく更新しない）。
    """
    deleted = existing.deleted_at is not None
    logger.warning(
        f"Photo {existing.id} already exists (deleted={deleted}); "
        "returning the existing record without re-processing"
    )
    return {
        "success": True,
        "duplicate": True,
        "deleted": deleted,
        "id": str(existing.id),
        "photo_id": str(existing.id),
        "person_detected": existing.person_detected,
        "captured_at": (
            existing.captured_at.isoformat() if existing.captured_at else None
        ),
        "ai_detection_status": existing.ai_detection_status,
        "file_path": existing.file_path,
        "original_filename": original_name,
        "message": (
            "この写真は既に登録済です（削除済）"
            if deleted
            else "この写真は既に登録済です"
        ),
    }


@router.post("/upload", response_model=None)
async def upload_photo(
    file: UploadFile,
    original_filename: str | None = Form(None),
    captured_date: str | None = Form(None),  # YYYY-MM-DD format
    source: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Upload and process photo for person detection."""
    try:
        # Skip heavy model imports for faster upload - Issue #400 moves this to background
        model = None  # Skip YOLO model loading during upload for performance
        logger.info(
            "Skipping YOLO model loading during upload for improved performance"
        )

        log_with_context(
            logger,
            "info",
            "Photo upload started",
            filename=file.filename,
            content_type=file.content_type,
        )

        contents = await read_upload_capped(file, MAX_IMAGE_UPLOAD_BYTES)
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(
                status_code=400, detail="Invalid image file - could not decode"
            )

        log_with_context(
            logger,
            "info",
            "Image decoded successfully",
            image_shape=img.shape,
            file_size_bytes=len(contents),
        )

        person_detected = False
        confidence_scores: list[float] = []
        detection_count = 0
        detection_time = 0

        # Skip YOLO inference during upload - moved to background processing for Issue #400
        # This significantly reduces upload time from several seconds to milliseconds
        logger.info(
            "Skipping YOLO inference during upload for improved performance - will be done in background"
        )

        # Extract photo_id from original filename if it matches camera format
        original_name = (
            original_filename or getattr(file, "filename", None) or "unknown.jpg"
        )

        # Check if filename matches camera service format: photo_YYYYMMDD_HHMMSS.jpg
        camera_pattern = r"^photo_(\d{8}_\d{6})\.jpg$"
        match = re.match(camera_pattern, original_name)

        if match:
            # Use the same ID as camera service expects (without extension)
            photo_id = f"photo_{match.group(1)}"
            logger.info(f"Using camera-generated photo ID: {photo_id}")
        else:
            # Generate UUID for non-camera uploads
            photo_id = str(uuid.uuid4())
            logger.info(f"Generated new UUID for non-camera upload: {photo_id}")

        safe_filename = f"{photo_id}.jpg"

        # 同じ photo_id は 1 度しか受け付けない。ここで返して以降の保存・
        # バックグラウンド処理をすべて飛ばす。lookup が落ちたときは先へ進めて、DB の
        # 一意制約（IntegrityError）を最後の砦にする
        if DB_AVAILABLE and db:
            try:
                existing_photo = PhotoRepository(db).get_by_id_including_deleted(
                    photo_id
                )
                if existing_photo:
                    return _duplicate_response(existing_photo, original_name)
            except Exception as e:
                logger.error(f"Error checking for duplicate photo: {e}")

        debug_msg = f"DEBUG: original_name={original_name}, safe_filename={safe_filename}, photo_id={photo_id}"
        print(debug_msg)
        logger.info(debug_msg)
        logger.info(
            f"Processing upload: original_filename={original_name}, safe_filename={safe_filename}, photo_id={photo_id}"
        )

        # Parse captured date if provided (JST統一)
        if captured_date:
            try:
                # YYYY-MM-DD形式をJST正午として解析
                timestamp = TimezoneUtils.parse_date_as_jst_noon(captured_date)
                logger.info(f"Using specified capture date (JST): {timestamp}")
            except ValueError as e:
                logger.warning(
                    f"Invalid date format '{captured_date}', using current JST time: {e}"
                )
                timestamp = jst_now()
        else:
            timestamp = jst_now()

        # Use ImageUploadService for consistent storage (GCS or local)
        # ⚠️ 冪等なのは DB レコードだけ。同じ photo_id の 2 リクエストがここを同時に
        # 通ると、GCS の同じキーへ両方が書く（後勝ち）。中身が違えば、残る行の
        # メタデータと保存された画像がずれる。塞がないと決めた:
        # 同時に通りうる 2 経路（タッチスクリーン UI・Pi の再送）はどちらもカメラの
        # photos_dir にある同じファイルを送る（UI は camera_service の /photos/{id} を
        # そのまま上げ、その endpoint は FileResponse で実体を返す）ので中身が一致し、
        # 上書きしても保存画像も file_size も変わらない。中身の違う 2 枚を同じ
        # photo_id にできる経路はあるが（手動アップロードで photo_YYYYMMDD_HHMMSS.jpg
        # という名前を選ぶ）、非同時なら上の存在確認が duplicate を返してここへ来ない
        from ..image_upload_service import get_image_upload_service

        # Reset file pointer for upload service
        await file.seek(0)
        upload_service = get_image_upload_service()

        try:
            # Upload photo using dedicated method (not wardrobe method)
            upload_result = await upload_service.upload_photo(contents, photo_id)
            photo_url = upload_result["url"]
            logger.info(f"Photo uploaded to GCS via ImageUploadService: {photo_url}")
        except Exception as upload_error:
            logger.warning(
                f"ImageUploadService GCS upload failed, falling back to local: {upload_error}"
            )
            # Fallback to local storage
            photos_dir = os.path.expanduser(os.getenv("PHOTOS_DIR", "photos"))
            os.makedirs(photos_dir, exist_ok=True)

            photo_path = os.path.join(photos_dir, safe_filename)
            with open(photo_path, "wb") as file:
                file.write(contents)
            photo_url = f"photos/{safe_filename}"
            logger.info(f"Photo saved to local disk: {photo_path}")

        # Storage handler update removed - data should be persisted in database only
        logger.info(f"Photo {photo_id} uploaded successfully")

        # Skip synchronous clothing detection - will be done in background by Issue #400
        # This significantly improves upload performance
        clothing_items: list[str] = []  # 空配列でバックグラウンド処理完了を待つ
        logger.info(
            "Skipping synchronous AI detection, will be processed in background by RQ worker"
        )

        # Save to database using repository if available
        if DB_AVAILABLE and db:
            try:
                repo = PhotoRepository(db)

                photo = repo.create(
                    photo_id=photo_id,
                    filename=safe_filename,
                    file_path=photo_url,
                    source=_resolve_source(source),
                    captured_at=timestamp,
                    person_detected=person_detected,
                    confidence_score=(
                        max(confidence_scores) if confidence_scores else None
                    ),
                    detection_count=detection_count,
                    clothing_items=clothing_items,
                    file_size=len(contents),
                    processing_time_ms=detection_time if model else None,
                    model_version="roboflow_clothing_segmentation",
                )
                # Store database ID but keep original photo_id for consistency
                db_photo_id = str(photo.id)
                logger.info(
                    f"Created database record with ID {db_photo_id} for photo {photo_id}"
                )

                # アップロード完了後、AI検出をバックグラウンドで実行（スレッドプール使用）
                logger.info(f"🚀 Starting background AI detection for photo {photo_id}")

                def run_ai_detection_sync() -> None:
                    """同期実行用のラッパー関数."""
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            loop.run_until_complete(
                                run_ai_detection_with_new_session(photo_id)
                            )
                        finally:
                            loop.close()
                    except Exception as e:
                        logger.error(f"Background AI detection failed: {e}")
                        raise  # Re-raise for thread pool error handling

                # スレッドプールで実行（リソース制限とエラーハンドリング改善）
                future = AI_DETECTION_THREAD_POOL.submit(run_ai_detection_sync)

                # Add callback for error handling (non-blocking)
                def handle_ai_detection_result(future: Any) -> None:
                    try:
                        future.result()  # This will raise exception if the task failed
                        logger.info(
                            f"✅ Background AI detection completed for photo {photo_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ Background AI detection failed for photo {photo_id}: {e}"
                        )

                future.add_done_callback(handle_ai_detection_result)
                logger.info(
                    f"✅ Background AI detection queued in thread pool for photo {photo_id}"
                )

                # Google Photos へのアップロードもバックグラウンドで実行
                google_photos_future = AI_DETECTION_THREAD_POOL.submit(
                    upload_to_google_photos_background, photo_id, contents, timestamp
                )

                def handle_google_photos_result(future: Any) -> None:
                    try:
                        result = future.result()
                    except Exception as e:
                        logger.error(
                            f"❌ Background Google Photos upload failed for photo {photo_id}: {e}"
                        )
                        return
                    log_google_photos_upload_result(photo_id, result)

                google_photos_future.add_done_callback(handle_google_photos_result)
                logger.info(
                    f"✅ Background Google Photos upload queued for photo {photo_id}"
                )

                # その日に会った人の記録もバックグラウンドで実行。
                # ICS 取得が数秒かかるため応答のクリティカルパスに乗せない
                AI_DETECTION_THREAD_POOL.submit(record_attendees_background, photo_id)
                logger.info(f"✅ Background attendees recording queued for {photo_id}")

                log_with_context(
                    logger,
                    "info",
                    "Photo record created in database",
                    photo_id=photo_id,
                    db_id=db_photo_id,
                    person_detected=person_detected,
                )
            except Exception as db_error:
                # Explicitly rollback on any database error
                logger.error(f"Database save failed: {db_error}", exc_info=True)
                try:
                    db.rollback()
                    logger.info("Database transaction rolled back successfully")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback transaction: {rollback_error}")

                # 冒頭の存在確認と INSERT の間に別経路が入れた場合ここへ来る。409 を
                # 返すと Pi の再送が届く見込みのないまま失敗し続けるので、先に入った
                # レコードを返して冪等を成立させる。
                # 判定を下の文字列マッチに寄せないのは、ドライバが文言を変えたときに
                # 静かに 500 へ落ちるのを避けるため。行が実在するときだけ返すので、
                # 一意制約以外の IntegrityError は下の分類がそのまま効く
                if isinstance(db_error, IntegrityError):
                    existing_photo = None
                    try:
                        existing_photo = PhotoRepository(
                            db
                        ).get_by_id_including_deleted(photo_id)
                    except Exception as lookup_error:
                        logger.error(
                            f"Failed to look up conflicting photo {photo_id}: {lookup_error}"
                        )
                    if existing_photo:
                        return _duplicate_response(existing_photo, original_name)

                # 上で返せなかった＝行が実在しない。一意制約由来なら 409、それ以外は
                # 500 に振り分ける（IntegrityError の種別は型からは分からない）
                if "duplicate key" in str(db_error) or "UNIQUE constraint" in str(
                    db_error
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=f"Photo with ID {photo_id} already exists. Please try again.",
                    ) from db_error
                else:
                    raise HTTPException(
                        status_code=500, detail="Database save failed"
                    ) from db_error
        else:
            logger.warning("Database not available, saving only to filesystem")

        return {
            "success": True,
            "id": photo_id,  # Use original photo_id for consistency
            "photo_id": photo_id,  # Use original photo_id for consistency
            "person_detected": person_detected,
            "captured_at": (
                timestamp.isoformat() if timestamp else None
            ),  # 統一：captured_at
            "ai_detection_status": "pending",
            "file_path": photo_url,
            "original_filename": original_name,
            "message": (
                "人物が検出されました"
                if person_detected
                else "人物は検出されませんでしたが記録を作成しました"
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        error_details = {
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }
        logger.error(f"Photo upload failed: {error_details}", exc_info=True)
        raise HTTPException(status_code=500, detail="Upload failed") from e
