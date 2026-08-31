"""CORS ミドルウェア設定."""

import logging
import os
import socket
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

# credentials 付きレスポンスでは methods/headers をワイルドカードにしない（明示列挙）
ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Authorization", "Content-Type", "X-External-Rental-Token"]


def setup_cors(app: FastAPI) -> None:
    """CORS ミドルウェアを設定."""
    # UI_PORT を使用（デフォルトは 3000）
    ui_port = os.getenv("UI_PORT", "3000")

    # 基本的な許可オリジン
    allowed_origins = [f"http://localhost:{ui_port}", f"http://127.0.0.1:{ui_port}"]

    # 本番環境とRaspberry Pi環境の設定
    env = os.getenv("ENV", "development")
    if env == "production":
        # 本番環境: Cloudflare 経由のドメインアクセスのみ許可。
        # PRODUCTION_DOMAIN 未設定なら fail-closed（プレースホルダを暗黙信頼しない）
        production_domain = os.getenv("PRODUCTION_DOMAIN")
        if production_domain:
            allowed_origins = [
                f"https://app.{production_domain}",  # メインアプリ
                f"https://{production_domain}",  # ルートドメイン
            ]
        else:
            logger.error(
                "ENV=production だが PRODUCTION_DOMAIN が未設定。CORS 許可オリジンを空にします。"
            )
            allowed_origins = []
    elif "pi-camera" in socket.gethostname():
        # Raspberry Pi環境: ローカルネットワークアクセスを追加
        allowed_origins.extend(
            [
                "http://pi-camera.local:3000",
                f"http://pi-camera.local:{ui_port}",
            ]
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
    )
