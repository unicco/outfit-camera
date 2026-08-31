"""カメラサービスプロキシエンドポイント."""

import asyncio
import logging
import os
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/camera", tags=["camera"])

# カメラサービスURL
CAMERA_SERVICE_URL = os.getenv("CAMERA_URL", "http://localhost:8001")


async def stream_camera_feed() -> AsyncGenerator[bytes, None]:
    """カメラフィードをストリーミング."""
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            logger.info(
                f"🎥 Connecting to camera service at {CAMERA_SERVICE_URL}/stream"
            )

            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                async with client.stream(
                    "GET", f"{CAMERA_SERVICE_URL}/stream"
                ) as response:
                    response.raise_for_status()

                    logger.info("✅ Successfully connected to camera stream")
                    retry_count = 0  # Reset retry count on successful connection

                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            yield chunk
                        await asyncio.sleep(0.01)  # 10ms delay to reduce CPU usage

        except httpx.ConnectError as e:
            logger.error(f"❌ Failed to connect to camera service: {e}")
            retry_count += 1
            if retry_count >= max_retries:
                logger.error(f"🚨 Max retries ({max_retries}) reached. Giving up.")
                yield b"--frame\r\nContent-Type: text/plain\r\n\r\nCamera service unavailable\r\n"
                break
            else:
                logger.info(f"🔄 Retrying connection ({retry_count}/{max_retries})...")
                await asyncio.sleep(2)  # Wait before retry

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Camera service returned error: {e.response.status_code}")
            yield b"--frame\r\nContent-Type: text/plain\r\n\r\nCamera service error\r\n"
            break

        except Exception as e:
            logger.error(f"❌ Unexpected error in camera stream: {e}")
            retry_count += 1
            if retry_count >= max_retries:
                yield b"--frame\r\nContent-Type: text/plain\r\n\r\nCamera stream error\r\n"
                break
            await asyncio.sleep(2)


@router.get("/stream")
async def camera_stream(request: Request) -> StreamingResponse:
    """カメラストリームをプロキシ.

    TouchScreen component からのリクエストをカメラサービスにプロキシします。
    """
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"📹 Camera stream requested from {client_host}")

    # Check if camera service is available
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0)
        ) as client:
            health_response = await client.get(f"{CAMERA_SERVICE_URL}/health")
            if health_response.status_code != 200:
                logger.warning(
                    f"Camera service health check failed: {health_response.status_code}"
                )
    except Exception as e:
        logger.error(f"Camera service is not available: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Camera service is not available at {CAMERA_SERVICE_URL}",
        )

    return StreamingResponse(
        stream_camera_feed(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


@router.head("/stream")
async def camera_stream_head() -> dict[str, str]:
    """カメラストリームのHEADリクエスト対応.

    ブラウザからのプリフライトリクエストに対応
    """
    return {
        "status": "available",
        "service": "camera-stream",
    }
