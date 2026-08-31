"""AI detection background processing service.

Handles background AI detection and thread pool management.
VLM-only pipeline (Roboflow/Jina embedding removed).
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Import database components with fallback
try:
    from ..repositories import PhotoRepository

    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    PhotoRepository = None  # type: ignore

# Thread pool for background AI detection
AI_DETECTION_THREAD_POOL = ThreadPoolExecutor(
    max_workers=3,  # Limit concurrent AI detection processes
    thread_name_prefix="ai_detection",
)


def _find_wardrobe_matches(wardrobe_matches: dict, category: str) -> list:
    """case-insensitive でワードローブマッチを検索."""
    # 完全一致
    if category in wardrobe_matches:
        return wardrobe_matches[category]
    # case-insensitive
    cat_lower = category.lower()
    for key, matches in wardrobe_matches.items():
        if key.lower() == cat_lower:
            return matches
    return []


async def run_ai_detection_with_new_session(photo_id: str) -> None:
    """新しいDBセッションでバックグラウンドAI検出を実行."""
    if not DB_AVAILABLE:
        logger.warning("Database not available, skipping AI detection")
        return

    # 新しいセッションを作成
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        await run_ai_detection_background(photo_id, db)
        # Commit any pending changes
        db.commit()
        logger.info(f"AI detection database changes committed for photo {photo_id}")
    except Exception as e:
        # Rollback on error
        logger.error(f"Error in AI detection for photo {photo_id}: {e}")
        try:
            db.rollback()
            logger.info(f"Database transaction rolled back for photo {photo_id}")
        except Exception as rollback_error:
            logger.error(
                f"Failed to rollback AI detection transaction: {rollback_error}"
            )
        raise
    finally:
        db.close()


async def run_ai_detection_background(photo_id: str, db: Session) -> None:
    """バックグラウンドでAI検出を実行し、結果をデータベースに保存."""
    logger.info(f"Starting background AI detection for photo {photo_id}")

    try:
        from ..routers.ai_detection import ClothingDetectorV2

        # V2 検出器を初期化
        detector_v2 = ClothingDetectorV2()

        logger.info(f"Running AI detection v2 for photo {photo_id}")
        detection_result = detector_v2.process_photo(photo_id, db)
        logger.info(
            f"AI detection completed for photo {photo_id}, found {len(detection_result.detected_items)} items"
        )

        # PhotoRepositoryを使用してAI検出結果を更新
        if PhotoRepository is not None:
            repo = PhotoRepository(db)
            photo = repo.get_by_id(photo_id)
            if photo:
                # AI検出結果をPhoto モデルに保存
                clothing_items = []
                for item in detection_result.detected_items:
                    clothing_items.append(item.category)

                ai_detection_data = {
                    "photo_id": detection_result.photo_id,
                    "detection_count": len(detection_result.detected_items),
                    "detected_items": [
                        {
                            "category": item.category,
                            "confidence": item.confidence,
                            "bbox": item.bbox,
                            "cropped_image_url": item.cropped_image_url,
                            "wardrobe_match_candidates": [
                                {
                                    "wardrobe_item_id": match.item_id,
                                    "similarity_score": match.similarity,
                                    "name": match.name,
                                    "brand": match.brand,
                                    "subcategory": match.subcategory,
                                    "image_url": match.image_url,
                                }
                                for match in _find_wardrobe_matches(
                                    detection_result.wardrobe_matches,
                                    item.category,
                                )
                            ],
                        }
                        for item in detection_result.detected_items
                    ],
                    "background_removed_url": detection_result.background_removed_url,
                    "processing_time_ms": detection_result.processing_time_ms,
                    "model_version": "vlm_bulk",
                }

                update_data = {
                    "ai_detection_results": ai_detection_data,
                    "ai_detection_status": "completed",
                    "clothing_items": clothing_items,
                    "person_detected": len(detection_result.detected_items) > 0,
                    "detection_count": len(detection_result.detected_items),
                    "ai_cropped_images": [
                        item.cropped_image_url
                        for item in detection_result.detected_items
                        if item.cropped_image_url
                    ],
                }
                try:
                    repo.update(str(photo.id), **update_data)
                    logger.info(f"AI detection results saved for photo {photo_id}")
                except Exception as update_error:
                    logger.error(
                        f"Failed to update AI detection results: {update_error}"
                    )
                    raise
            else:
                logger.error(f"Photo {photo_id} not found in database")

    except Exception as e:
        logger.error(f"Background AI detection failed for photo {photo_id}: {e}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")

        # エラーが発生した場合はステータスを更新
        if PhotoRepository is not None:
            try:
                repo = PhotoRepository(db)
                repo.update(
                    photo_id, ai_detection_status="failed", ai_detection_error=str(e)
                )
            except Exception as status_update_error:
                logger.error(
                    f"Failed to update AI detection failed status: {status_update_error}"
                )


def shutdown_ai_detection_thread_pool() -> None:
    """アプリケーション終了時にスレッドプールを適切にシャットダウン."""
    try:
        logger.info("Shutting down AI detection thread pool...")
        AI_DETECTION_THREAD_POOL.shutdown(wait=True)
        logger.info("AI detection thread pool shutdown completed")
    except Exception as e:
        logger.error(f"Error during thread pool shutdown: {e}")


# Register shutdown handler (called by main.py startup event)
def register_shutdown_handler() -> None:
    """シャットダウンハンドラを登録."""
    import atexit

    atexit.register(shutdown_ai_detection_thread_pool)
