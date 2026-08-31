import logging

logger = logging.getLogger(__name__)


def setup_pytorch_compatibility() -> None:
    """Roboflow + GrabCut 使用時の互換性設定."""
    # Issue #905: YOLO を Roboflow + GrabCut に置き換えたため、PyTorch 設定は不要
    logger.info("Skipping PyTorch setup - using Roboflow + GrabCut API instead of YOLO")
