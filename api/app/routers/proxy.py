"""カメラサービスへのプロキシエンドポイント."""

import logging
import os

import httpx
from fastapi import APIRouter, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter()

# カメラサービスのURL
CAMERA_SERVICE_URL = os.getenv("CAMERA_URL", "http://localhost:8001")


@router.api_route(
    "/camera/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
)
async def camera_proxy(path: str, request: Request) -> Response:
    """カメラサービスへのプロキシエンドポイント
    /camera/* へのリクエストをカメラサービスに転送.
    """
    # ターゲットURLを構築
    target_url = f"{CAMERA_SERVICE_URL}/{path}"

    # クエリパラメータを追加
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    # リクエストボディを取得
    body = await request.body()

    # ヘッダーをコピー（Hostヘッダーは除外）
    headers = dict(request.headers)
    headers.pop("host", None)

    try:
        # プロキシリクエストを送信
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                follow_redirects=True,
            )

        # レスポンスヘッダーをコピー（一部は除外）
        excluded_headers = {
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        }
        proxy_headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in excluded_headers
        }

        # レスポンスを返す
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=proxy_headers,
            media_type=response.headers.get("content-type"),
        )

    except httpx.TimeoutException:
        logger.error(f"Timeout proxying request to camera service: {target_url}")
        return Response(content="Camera service timeout", status_code=504)
    except Exception as e:
        logger.error(f"Error proxying request to camera service: {e}")
        return Response(content=f"Camera service error: {str(e)}", status_code=502)
