"""API バージョン管理.

APIのバージョニングを管理し、適切なルーターに振り分ける
"""

import logging
from typing import Set
from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# サポートされているバージョン
SUPPORTED_VERSIONS: Set[str] = {"v2"}


def setup_api_versioning(app: FastAPI) -> None:
    """API バージョニングの設定.

    Args:
        app: FastAPI アプリケーション

    """

    # バージョン情報エンドポイント
    @app.get("/api/versions")
    async def get_api_versions() -> dict:
        """利用可能な API バージョンを返す."""
        return {
            "versions": [
                {
                    "version": "v2",
                    "status": "stable",
                    "deprecated": False,
                    "description": "新機能を含む次世代 API",
                    "base_path": "/api/v2",
                },
            ],
            "default_version": "v2",
            "latest_version": "v2",
            "supported_versions": list(SUPPORTED_VERSIONS),
        }

    @app.get("/api")
    async def get_api_root() -> dict:
        """API ルートのガイダンスを返す."""
        return {
            "message": "Coordinate Recorder API",
            "default_version": "v2",
            "latest_version": "v2",
            "versions_endpoint": "/api/versions",
        }

    @app.api_route(
        "/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
    )
    async def handle_unsupported_version(path: str) -> JSONResponse:
        """バージョン指定なしのリクエストに案内を返す."""
        logger.warning("Deprecated API path accessed: /api/%s", path)
        return JSONResponse(
            status_code=404,
            content={
                "error": "Not Found",
                "message": "This endpoint has been retired. Please migrate to /api/v2/…",
                "requested_path": f"/api/{path}",
                "versions_endpoint": "/api/versions",
            },
        )
