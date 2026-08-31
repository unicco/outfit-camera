"""AI clothing detection API v2 - VLM-only detection and wardrobe matching."""

import logging
import io
import time
from typing import List, Dict, Any, Optional
import uuid

import numpy as np
from PIL import Image
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

import requests
from pathlib import Path
import cv2

from ..database import get_db
from ..models import Photo
from ..services import item_color
from ..upload_limits import MAX_IMAGE_UPLOAD_BYTES, read_upload_capped
from ..url_safety import is_allowed_storage_url
from ..wardrobe_models import ClothingItem
from ..schemas.base import BaseModel
from ..image_upload_service import get_image_upload_service
from ..utils.wb_and_tone import ImageColorProcessor

from coordinate_recorder.vlm_clothing_detector import VLMClothingDetector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/ai", tags=["AI Detection V2"])


class DetectionRequestV2(BaseModel):
    """検出リクエスト."""

    photo_id: str
    apply_wb_correction: bool = True  # ホワイトバランス補正を適用


class DetectedItemV2(BaseModel):
    """検出されたアイテム."""

    category: str
    confidence: float
    cropped_image_url: str
    bbox: Dict[str, float]
    # 属性検出フィールド (Issue #1045)
    silhouette_type: Optional[str] = None  # tight, regular, loose
    sleeve_length: Optional[str] = (
        None  # long_sleeve, short_sleeve, sleeveless (トップスのみ)
    )
    attributes: Optional[Dict[str, Any]] = None  # その他の属性情報
    # パターン検出フィールド (Issue #1059)
    pattern_type: Optional[str] = None  # striped, gradient, rainbow, etc
    design_complexity: Optional[str] = None  # simple, moderate, complex


class WardrobeMatchV2(BaseModel):
    """ワードローブマッチ結果."""

    item_id: str
    name: str
    brand: Optional[str] = None
    subcategory: Optional[str] = None
    similarity: float
    image_url: Optional[str] = None


class DetectionResultV2(BaseModel):
    """検出結果."""

    photo_id: str
    background_removed_url: str
    detected_items: List[DetectedItemV2]
    wardrobe_matches: Dict[str, List[WardrobeMatchV2]]  # カテゴリ別のマッチ結果
    processing_time_ms: float


class ClothingDetectorV2:
    """VLM-only clothing detection system."""

    def __init__(self):
        self.upload_service = get_image_upload_service()
        self.vlm_detector = VLMClothingDetector()

        # ホワイトバランス処理インスタンス
        config_path = Path(__file__).parent.parent / "config" / "wb_config.json"
        self.wb_processor = ImageColorProcessor(
            str(config_path) if config_path.exists() else None
        )

    def process_photo(
        self, photo_id: str, db: Session, apply_wb_correction: bool = True
    ) -> DetectionResultV2:
        """写真を処理して服を検出・マッチング.

        VLM 一括マッチングのみで検出+マッチングを実行。
        """
        start_time = time.time()

        # 1. 写真を読み込み
        photo = db.query(Photo).filter(Photo.id == photo_id).first()
        if not photo:
            raise HTTPException(status_code=404, detail=f"Photo not found: {photo_id}")

        image = self._load_image(photo, apply_wb_correction=apply_wb_correction)

        # Convert PIL to numpy array
        original_array = np.array(image)
        if original_array.shape[2] == 4:
            original_array = original_array[:, :, :3]

        # 2. VLM 一括マッチングを実行
        logger.info("Step 1: VLM 一括検出+マッチング中...")
        vlm_result = self._detect_and_match_vlm(original_array, db)

        if vlm_result is None:
            logger.warning("VLM pipeline returned no results for photo %s", photo_id)
            processing_time = (time.time() - start_time) * 1000
            return DetectionResultV2(
                photo_id=photo_id,
                background_removed_url="",
                detected_items=[],
                wardrobe_matches={},
                processing_time_ms=processing_time,
            )

        # VLM 成功: 検出結果とマッチ結果を構築
        detected_items = []
        for detection in vlm_result["detections"]:
            detected_items.append(
                DetectedItemV2(
                    category=detection["type"],
                    confidence=detection["confidence"],
                    cropped_image_url="",  # VLM パイプラインでは切り抜きしない
                    bbox=detection["bbox"],
                )
            )

        wardrobe_matches = vlm_result["wardrobe_matches"]

        processing_time = (time.time() - start_time) * 1000
        logger.info(
            "VLM pipeline completed: %d items detected in %.0fms",
            len(detected_items),
            processing_time,
        )

        return DetectionResultV2(
            photo_id=photo_id,
            background_removed_url="",  # VLM パイプラインでは背景除去しない
            detected_items=detected_items,
            wardrobe_matches=wardrobe_matches,
            processing_time_ms=processing_time,
        )

    def _load_image(
        self, photo: Photo, apply_wb_correction: bool = True
    ) -> Image.Image:
        """写真を読み込み."""
        if photo.file_path.startswith("https://"):
            # GCS から読み込み（SSRF 対策: allowlist 済ホストのみ許可）
            if not is_allowed_storage_url(photo.file_path):
                raise ValueError(
                    f"Refusing to fetch non-allowlisted image URL: {photo.file_path}"
                )
            response = requests.get(photo.file_path, timeout=10, allow_redirects=False)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
        else:
            # ローカルから読み込み
            image = Image.open(photo.file_path).convert("RGB")

        # ホワイトバランス補正を適用
        if apply_wb_correction:
            try:
                corrected_bgr = self.wb_processor.process_image(
                    image, apply_wb=True, apply_tone=True
                )
                corrected_rgb = cv2.cvtColor(corrected_bgr, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(corrected_rgb)
                logger.debug("ホワイトバランス補正を適用しました")
            except Exception as e:
                logger.warning(f"ホワイトバランス補正の適用に失敗しました: {e}")

        return image

    def _detect_and_match_vlm(
        self, image: np.ndarray, db: Session
    ) -> Optional[Dict[str, Any]]:
        """VLM 一括検出+マッチング: 全身写真から衣類検出とワードローブマッチングを同時に実行.

        Returns:
            成功時: {"detections": [...], "wardrobe_matches": {...}}
            失敗時: None
        """
        if not self.vlm_detector or not self.vlm_detector.is_available:
            return None

        try:
            from ..wardrobe_models import ClothingStatus

            # ACTIVE なワードローブアイテムを取得
            items = (
                db.query(ClothingItem)
                .filter(ClothingItem.status == ClothingStatus.ACTIVE)
                .all()
            )

            if not items:
                logger.warning("No active wardrobe items found for VLM matching")
                return None

            # サムネイル画像をダウンロードして準備
            wardrobe_data = []
            for item in items:
                thumb_url = None
                if isinstance(item.image_urls, dict):
                    thumbs = item.image_urls.get("thumbnails", {})
                    thumb_url = thumbs.get("thumb_200") or item.image_urls.get(
                        "original"
                    )
                elif isinstance(item.image_urls, list) and item.image_urls:
                    thumb_url = item.image_urls[0]

                if not thumb_url:
                    continue

                # SSRF 対策: allowlist 済ホスト以外は取得しない
                if not is_allowed_storage_url(thumb_url):
                    logger.warning(
                        "Skipping non-allowlisted wardrobe thumbnail URL for item %s",
                        item.id,
                    )
                    continue

                try:
                    resp = requests.get(thumb_url, timeout=5, allow_redirects=False)
                    if not resp.ok:
                        continue
                    wardrobe_data.append(
                        {
                            "id": item.id,
                            "name": item.name,
                            "category": (
                                item.category
                                if isinstance(item.category, str)
                                else item.category.value
                            ),
                            "subcategory": item.subcategory or "",
                            "thumbnail": resp.content,
                        }
                    )
                except Exception as e:
                    logger.debug("Failed to download thumbnail for %s: %s", item.id, e)
                    continue

            if not wardrobe_data:
                return None

            logger.info(
                "VLM bulk matching: %d wardrobe items loaded", len(wardrobe_data)
            )

            # VLM 一括マッチング実行
            vlm_matches = self.vlm_detector.match_with_wardrobe(image, wardrobe_data)

            if not vlm_matches:
                return None

            # 検出結果を構築
            h, w = image.shape[:2]
            detections = []
            for m in vlm_matches:
                item_type = m.get("type", "unknown")
                position = m.get("position", "full_body")
                bbox = self.vlm_detector._position_to_bbox(position, w, h)
                detections.append(
                    {
                        "type": item_type,
                        "color": m.get("color", ""),
                        "color_hex": m.get("color_hex", ""),
                        "position": position,
                        "confidence": float(m.get("confidence", 0.8)),
                        "bbox": bbox,
                    }
                )

            # ワードローブマッチ結果を WardrobeMatchV2 形式に変換
            item_map = {item.id: item for item in items}

            # VLM が返した color_hex をマッチしたワードローブアイテムに反映
            self._update_wardrobe_colors(vlm_matches, item_map, db)
            wardrobe_matches: Dict[str, List[WardrobeMatchV2]] = {}

            for m in vlm_matches:
                item_type = m.get("type", "unknown").lower()
                candidates = m.get("wardrobe_candidates", [])

                # 旧形式との後方互換（wardrobe_item_id のみ）
                if not candidates:
                    wid = m.get("wardrobe_item_id")
                    if wid:
                        candidates = [
                            {
                                "wardrobe_item_id": wid,
                                "confidence": m.get("confidence", 0.8),
                            }
                        ]

                if item_type not in wardrobe_matches:
                    wardrobe_matches[item_type] = []

                for c in candidates:
                    wardrobe_id = c.get("wardrobe_item_id")
                    if wardrobe_id and wardrobe_id in item_map:
                        db_item = item_map[wardrobe_id]
                        thumb_url = None
                        if isinstance(db_item.image_urls, dict):
                            thumbs = db_item.image_urls.get("thumbnails", {})
                            thumb_url = thumbs.get(
                                "thumb_200"
                            ) or db_item.image_urls.get("original")

                        wardrobe_matches[item_type].append(
                            WardrobeMatchV2(
                                item_id=db_item.id,
                                name=db_item.name,
                                brand=db_item.brand,
                                subcategory=db_item.subcategory,
                                similarity=float(c.get("confidence", 0.8)),
                                image_url=thumb_url,
                            )
                        )

            logger.info(
                "VLM bulk matching result: %s",
                {k: len(v) for k, v in wardrobe_matches.items()},
            )
            return {
                "detections": detections,
                "wardrobe_matches": wardrobe_matches,
            }

        except Exception as e:
            logger.error("VLM bulk wardrobe matching failed: %s", e)
            return None

    @staticmethod
    def _update_wardrobe_colors(
        vlm_matches: List[Dict[str, Any]],
        item_map: Dict[str, ClothingItem],
        db: Session,
    ) -> None:
        """VLM が返した color_hex をマッチしたワードローブアイテムの colors_palette に反映."""
        updated = 0

        for m in vlm_matches:
            color_hex = m.get("color_hex", "")
            if not color_hex or not item_color.is_valid_hex(color_hex):
                continue

            # 最も confidence が高い候補のワードローブアイテムを取得
            candidates = m.get("wardrobe_candidates", [])
            if not candidates:
                wid = m.get("wardrobe_item_id")
                if wid:
                    candidates = [{"wardrobe_item_id": wid}]

            for c in candidates[:1]:  # best match のみ
                wid = c.get("wardrobe_item_id")
                if not wid or wid not in item_map:
                    continue

                item = item_map[wid]
                existing = item.colors_palette or {}

                # 人が決めた色と、物撮りから取った色には触らない。VLM が返すのは
                # 実測値ではなく CSS の名前付きカラーで（実測 35 件が #000000 や
                # #FFFFFF に丸まっていた）、明度の材料にならない。
                # 手動レコードは palette を持たない形もあるので方式でも見る
                if item_color.is_manually_set(existing) or existing.get("palette"):
                    continue

                item.colors_palette = {
                    "palette": [{"hex": color_hex, "position": 1}],
                    "extraction_method": "vlm_gemini",
                }
                updated += 1

        if updated:
            try:
                db.flush()
                logger.info(
                    "Updated colors_palette for %d wardrobe items via VLM", updated
                )
            except Exception as e:
                logger.warning("Failed to update wardrobe colors: %s", e)


# グローバルインスタンス
_detector_v2 = None


def get_detector_v2() -> ClothingDetectorV2:
    """検出器のシングルトンインスタンスを取得."""
    global _detector_v2
    if _detector_v2 is None:
        _detector_v2 = ClothingDetectorV2()
    return _detector_v2


@router.post("/detect", response_model=DetectionResultV2)
async def detect_clothing_v2(
    request: DetectionRequestV2, db: Session = Depends(get_db)
) -> DetectionResultV2:
    """写真から服を検出してワードローブとマッチング."""
    detector = get_detector_v2()

    try:
        result = detector.process_photo(
            request.photo_id, db, apply_wb_correction=request.apply_wb_correction
        )
        logger.info(f"Detection completed in {result.processing_time_ms:.0f}ms")
        return result

    except Exception as e:
        logger.error(f"Detection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Detection failed")


@router.post("/detect-file")
async def detect_clothing_from_file(
    file: UploadFile = File(...),
    apply_wb_correction: bool = True,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """アップロードされたファイルから VLM で服を検出（テスト用）."""
    detector = get_detector_v2()

    try:
        # ファイルを読み込む（サイズ上限で DoS を防ぐ）
        contents = await read_upload_capped(file, MAX_IMAGE_UPLOAD_BYTES)
        image = Image.open(io.BytesIO(contents)).convert("RGB")

        # 一時的なphoto_idを生成
        temp_photo_id = str(uuid.uuid4())

        # 画像を処理
        start_time = time.time()

        # ホワイトバランス補正
        if apply_wb_correction:
            try:
                wb_processor = ImageColorProcessor()
                corrected_bgr = wb_processor.process_image(
                    image, apply_wb=True, apply_tone=True
                )
                corrected_rgb = cv2.cvtColor(corrected_bgr, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(corrected_rgb)
            except Exception as e:
                logger.warning(f"WB correction failed: {e}")

        # VLM で検出+マッチング
        original_array = np.array(image)
        if len(original_array.shape) == 3 and original_array.shape[2] == 4:
            original_array = original_array[:, :, :3]

        vlm_result = detector._detect_and_match_vlm(original_array, db)

        results = []
        if vlm_result:
            for detection in vlm_result["detections"]:
                item_type = detection["type"]
                matches = [
                    {
                        "wardrobe_item_id": m.item_id,
                        "similarity_score": m.similarity,
                        "name": m.name,
                        "brand": m.brand,
                        "subcategory": m.subcategory,
                        "image_url": m.image_url,
                    }
                    for m in vlm_result["wardrobe_matches"].get(item_type.lower(), [])
                ]
                results.append(
                    {
                        "category": item_type,
                        "confidence": detection["confidence"],
                        "bbox": detection["bbox"],
                        "wardrobe_match_candidates": matches,
                    }
                )

        processing_time = (time.time() - start_time) * 1000

        return {
            "temp_photo_id": temp_photo_id,
            "detected_items": results,
            "detection_count": len(results),
            "processing_time_ms": processing_time,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File detection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="File detection failed")
