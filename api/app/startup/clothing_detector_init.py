import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def init_clothing_detector() -> Optional[Any]:
    """ClothingDetector 初期化 (スタブ - V2 APIを使用)."""
    logger.info(
        "🔧 ClothingDetector initialization skipped - using V2 API (Roboflow + GrabCut)"
    )
    logger.info("✅ All AI detection is handled by routers/ai_detection.py")
    return None
