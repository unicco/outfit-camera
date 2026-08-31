"""リファクタリング完了版メインアプリケーション.

旧 main.py (1018行) から main_v2.py (186行) への完全移行により
約82%のコード削減と保守性の向上を実現
"""

import logging
import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

# パスを追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI  # noqa: E402
from .core.lifecycle import lifespan  # noqa: E402
from .settings import get_settings  # noqa: E402
from .middleware.cors import setup_cors  # noqa: E402
from .middleware.read_only import setup_read_only_middleware  # noqa: E402

# ルーターのインポート（core + cv2 非依存の feature router は import が常に安全）。
# cv2/libGL 依存の 3 本（upload / wardrobe / ai_detection）は下の
# _CV2_ROUTERS で個別ロードするため、ここでは import しない。
from .routers import (  # noqa: E402
    co_occurrence,
    external_rentals,
    google_photos,
    health,
    misc,
    morning_brief,
    outfit_similarity,
    outfits,
    photos,
    proxy,
    recommendations,
    records,
    session,
    status,
    wardrobe_analytics,
    wardrobe_processing,
)
from .routers.api_versions import setup_api_versioning  # noqa: E402

# ロギング設定
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# === 機能ルーター登録のメタ情報 ===
# ALL_FEATURE_ROUTERS: アプリが読み込む feature router 名の全集合。ルート集合
# スナップショットの安全網テスト（tests/backend/unit/test_route_snapshot.py）が
# 「全 feature router がロードされたか（＝依存が揃った環境か）」の判定に使う。
ALL_FEATURE_ROUTERS = frozenset(
    {
        "status",
        "outfit_similarity",
        "misc",
        "wardrobe_analytics",
        "wardrobe_processing",
        "outfits",
        "co_occurrence",
        "google_photos",
        "recommendations",
        "morning_brief",
        "external_rentals",
        "upload",
        "wardrobe",
        "ai_detection",
    }
)

# cv2/libGL 依存の feature router。モジュール冒頭で `import cv2` するため、libGL を
# 入れていない headless CI では import が失敗する。個別ロードして失敗を握り、他 router
# でアプリを起動継続する（本番 VPS は deploy/setup-vps.sh が libGL を導入するので全て
# ロードされる。）。
_CV2_ROUTERS = [
    ("upload", "app.routers.upload", "Upload"),
    ("wardrobe", "app.routers.wardrobe", "Wardrobe"),
    ("ai_detection", "app.routers.ai_detection", "AI Detection V2"),
]

# FastAPI アプリケーションの作成
app = FastAPI(
    title="Coordinate Recorder API",
    description="コーディネート記録システムのバックエンド API",
    version="3.0.0",
    lifespan=lifespan,
)

# ミドルウェアの設定
setup_cors(app)
setup_read_only_middleware(app)

# === Router 登録 ===
# 共通（core）router
app.include_router(health.router)
app.include_router(photos.router)
app.include_router(records.router)
app.include_router(proxy.router, tags=["proxy"])
app.include_router(session.router, tags=["auth"])

# cv2 非依存の feature router を明示登録。実際に登録した名前を loaded_routers に
# 記録する（安全網テスト・test_main が「どの router がロードされたか」を参照する）。
# 登録順は挙動に影響しない（feature router 間で path は重複しない）。ワイルドカードの
# API バージョニングだけは最後に登録する。
loaded_routers: dict[str, Any] = {}
for name, module in (
    ("status", status),
    ("outfit_similarity", outfit_similarity),
    ("misc", misc),
    ("wardrobe_analytics", wardrobe_analytics),
    ("wardrobe_processing", wardrobe_processing),
    ("outfits", outfits),
    ("co_occurrence", co_occurrence),
    ("google_photos", google_photos),
    ("recommendations", recommendations),
    ("morning_brief", morning_brief),
    ("external_rentals", external_rentals),
):
    app.include_router(module.router)
    loaded_routers[name] = module.router

# cv2/libGL 依存の feature router は個別ロードして import 失敗を許容する（上記 _CV2_ROUTERS
# のコメント参照）。headless CI では欠落するが、他 router でアプリは起動継続する。
for name, import_path, display_name in _CV2_ROUTERS:
    try:
        module = import_module(import_path)
        app.include_router(module.router)
        loaded_routers[name] = module.router
        logger.info(f"✅ {display_name} router registered")
    except Exception as e:
        logger.warning(
            f"⚠️  {display_name} router unavailable (cv2/libGL?): "
            f"{type(e).__name__}: {e}"
        )

# API バージョニングの設定（ワイルドカードルートは最後に登録）
setup_api_versioning(app)


# ルートエンドポイント
@app.get("/")
async def root() -> dict[str, Any]:
    """ルートエンドポイント."""
    settings = get_settings()
    return {
        "service": "Coordinate Recorder API",
        "version": "3.0.0",
        "status": "running",
        "storage_type": settings.storage_type,
        "database_enabled": settings.db_enabled,
    }


# エラーハンドラー
from fastapi.responses import JSONResponse  # noqa: E402


@app.exception_handler(404)
async def not_found_handler(request: Any, exc: Any) -> JSONResponse:
    """404 エラーハンドラー."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": f"Path {request.url.path} not found",
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request: Any, exc: Any) -> JSONResponse:
    """500 エラーハンドラー."""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
        },
    )




if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", "8000"))
    # 開発用の直接起動パス（reload=True）。本番は systemd が
    # `uvicorn --host 127.0.0.1` で起動するのでここは通らない
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # noqa: S104
        port=port,
        reload=True,
        log_level="info",
    )
