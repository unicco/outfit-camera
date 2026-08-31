import gc
import logging
from typing import Any

import psutil

from .clothing_detector_init import init_clothing_detector
from .model_loader import try_load_model_candidates
from .model_performance import log_memory_usage, validate_model_performance
from .pytorch_setup import setup_pytorch_compatibility

logger = logging.getLogger(__name__)


def init_models(disable_ai_features: bool, skip_model_loading: bool) -> tuple[Any, Any]:
    """AI モデルと ClothingDetector の初期化.

    Args:
        disable_ai_features: AI機能を無効化するかどうか
        skip_model_loading: モデルのロードをスキップするかどうか

    Returns:
        tuple: (model, clothing_detector) - 両方ともNoneの場合もある

    """
    # AI機能が無効化されている場合はスキップ
    if disable_ai_features or skip_model_loading:
        logger.info("🚫 AI features disabled: Skipping model initialization")
        return None, None

    # メモリ使用量監視
    process = psutil.Process()
    memory_before = process.memory_info().rss / 1024 / 1024  # MB
    logger.info(f"Memory before model init: {memory_before:.1f} MB")

    model = None
    clothing_detector = None

    try:
        logger.info("Loading AI model with memory optimization...")

        # PyTorch 互換性設定
        setup_pytorch_compatibility()

        # 既存モデルがある場合はクリーンアップ
        gc.collect()  # 強制ガベージコレクション

        # AI モデル候補をロード
        model = try_load_model_candidates()

        # ClothingDetector 初期化
        clothing_detector = init_clothing_detector()

        # メモリ使用量確認とクリーンアップ
        log_memory_usage(memory_before)
        validate_model_performance()

    except Exception as e:
        logger.error(f"Failed to initialize models: {e}")
        model = None
        clothing_detector = None

    return model, clothing_detector
