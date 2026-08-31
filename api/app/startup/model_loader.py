import logging
from typing import Optional

logger = logging.getLogger(__name__)


def try_load_model_candidates() -> Optional[object]:
    """AI モデルの初期化（V2 API へ移行）."""
    # Issue #905: YOLO を Roboflow + GrabCut (V2 API) に置き換え
    logger.info("Using Roboflow + GrabCut for clothing detection (V2 API)")

    # V2 API は独立して動作するため、ここでの初期化は不要
    # routers/ai_detection.py がすべての AI 検出を処理
    return None
