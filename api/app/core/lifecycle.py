"""アプリケーションのライフサイクル管理（起動・終了処理）."""

import gc
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import psutil
from fastapi import FastAPI

from ..automation import start_automation_services, stop_automation_services
from ..database import check_database_connection
from ..settings import get_settings

logger = logging.getLogger(__name__)


def _prepare_runtime_directories() -> None:
    """必須ディレクトリの作成と設定検証.

    以前は core/config.py の import 副作用（mkdir・print・validate_config）
    として実行されていた処理を、起動 lifespan に移設したもの。
    """
    settings = get_settings()

    for directory in (settings.photos_dir, settings.data_dir, settings.logs_dir):
        Path(directory).mkdir(parents=True, exist_ok=True)

    logger.info(f"Photos directory: {settings.photos_dir}")
    logger.info(f"Log directory: {settings.logs_dir}")

    # GCS を使用する場合の必須設定確認（旧 validate_config の例外送出を維持）
    if settings.storage_type == "gcs" and not settings.gcs_bucket_name:
        raise ValueError("GCS_BUCKET_NAME is required when STORAGE_TYPE=gcs")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """アプリケーションのライフサイクル管理."""
    # 起動処理
    logger.info("Starting up backend services...")

    # ディレクトリ作成と設定検証（旧 core/config.py の import 副作用）
    _prepare_runtime_directories()

    settings = get_settings()

    # アプリケーション情報の表示
    logger.info("Backend application starting up")
    logger.info(f"Storage type: {settings.storage_type}")
    logger.info(f"Database enabled: {settings.db_enabled}")

    if settings.storage_type == "gcs":
        logger.info("GCS専用モード: すべての画像はGCSから直接配信")

    # データベース接続確認
    if settings.db_enabled:
        try:
            if check_database_connection():
                logger.info("Database connection established successfully")
        except Exception as e:
            logger.warning(f"Database connection check failed: {e}")

    # 自動化サービスの開始
    if settings.db_enabled:
        start_automation_services()
        logger.info("Automation services started")

    # API キーの設定（V2 API では不要）
    # NOTE: Gemini は削除され、Roboflow + GrabCut (V2 API) を使用

    # AI モデルの初期化
    from ..startup.model_init import init_models

    # AI 機能が無効化されているかチェック
    disable_ai = os.getenv("DISABLE_AI_FEATURES", "false").lower() == "true"
    skip_models = os.getenv("SKIP_MODEL_LOADING", "false").lower() == "true"

    init_models(disable_ai, skip_models)

    # 写真ディレクトリの初期化（削除済 - データベースベースのアプローチを使用）
    # load_initial_photos(PHOTOS_DIR)

    yield

    # 終了処理
    logger.info("Shutting down backend services...")

    # メモリクリーンアップ
    logger.info("Cleaning up models and memory...")

    # V2 API を使用するため、ClothingDetector のクリーンアップは不要
    # NOTE: すべての AI 検出は routers/ai_detection.py で処理される

    # ガベージコレクション実行
    gc.collect()

    # メモリ使用量をログ
    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024
    logger.info(f"Memory after cleanup: {memory_mb:.1f} MB")
    logger.info("Memory cleanup completed")

    # 自動化サービスの停止
    if get_settings().db_enabled:
        stop_automation_services()
        logger.info("Automation services stopped")
    else:
        logger.info("File-based mode - no automation services to stop")
