"""ヘルスチェックエンドポイント."""

import os
import platform
import time
from datetime import datetime

import psutil
from fastapi import APIRouter
from sqlalchemy import text

from ..database import get_db
from ..settings import get_settings

API_VERSION = os.getenv("API_VERSION", "3.0.0")

router = APIRouter(tags=["health"])

# グローバル起動時刻
startup_time = time.time()


@router.get("/health")
async def health_check() -> dict:
    """システムヘルスチェック."""
    uptime_seconds = int(time.time() - startup_time)
    uptime_minutes = uptime_seconds // 60
    uptime_hours = uptime_minutes // 60

    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024
    cpu_percent = process.cpu_percent(interval=0.1)

    health_info = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "coordinate-recorder-api",
        "version": API_VERSION,
        "uptime": {
            "seconds": uptime_seconds,
            "formatted": f"{uptime_hours}h {uptime_minutes % 60}m {uptime_seconds % 60}s",
        },
        "system": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "memory_mb": round(memory_mb, 2),
            "cpu_percent": round(cpu_percent, 2),
        },
    }

    # データベース接続確認
    if get_settings().db_enabled:
        try:
            db = next(get_db())
            db.execute(text("SELECT 1"))
            health_info["database"] = {"status": "connected"}
        except Exception as e:
            # 本番環境では詳細エラーを隠す
            error_detail = (
                str(e)
                if os.getenv("ENV", "development") == "development"
                else "Database connection failed"
            )
            health_info["database"] = {"status": "disconnected", "error": error_detail}
        finally:
            if "db" in locals():
                db.close()
    else:
        health_info["database"] = {"status": "disabled"}

    return health_info


# v2 API 互換パス
router.add_api_route(
    path="/api/v2/health",
    endpoint=health_check,
    methods=["GET"],
    tags=["health"],
)
