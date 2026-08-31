import gc
import logging

import psutil

logger = logging.getLogger(__name__)


def validate_model_performance() -> None:
    """モデル性能検証とメモリ監視."""
    try:
        process = psutil.Process()
        memory_after = process.memory_info().rss / 1024 / 1024  # MB

        # メモリ使用量が1GB超過の場合は警告
        if memory_after > 1024:
            logger.warning(f"High memory usage detected: {memory_after:.1f} MB")
            # 強制ガベージコレクション実行
            gc.collect()

            # メモリ状況再確認
            memory_cleaned = process.memory_info().rss / 1024 / 1024  # MB
            logger.info(f"Memory after cleanup: {memory_cleaned:.1f} MB")

    except Exception as e:
        logger.error(f"Failed to validate model performance: {e}")


def log_memory_usage(before_memory: float) -> None:
    """メモリ使用量ログ出力."""
    try:
        process = psutil.Process()
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = memory_after - before_memory
        logger.info(
            f"Memory after model init: {memory_after:.1f} MB (+{memory_increase:.1f} MB)"
        )

    except Exception as e:
        logger.error(f"Failed to log memory usage: {e}")
