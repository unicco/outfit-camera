#!/usr/bin/env python3
"""outfit_api.py の 500 エラーを特定するためのデバッグスクリプト.

特に以下の箇所をテスト：
1. /api/v2/outfits/photo/{photo_id} エンドポイント
2. colors_palette フィールドアクセス
3. clothing_item データ取得
4. JSON シリアライゼーション
"""

import json
import logging
import sys
import traceback

import httpx

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8014"


def test_outfit_photo_endpoint(photo_id: str = "manual-2025-07-24"):
    """Outfit photo エンドポイントをテストして500エラーを確認."""
    url = f"{API_BASE_URL}/api/v2/outfits/photo/{photo_id}"

    try:
        logger.info(f"Testing endpoint: {url}")

        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)

            logger.info(f"Status code: {response.status_code}")
            logger.info(f"Headers: {dict(response.headers)}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.info("Response JSON structure:")
                    logger.info(
                        json.dumps(data, indent=2, ensure_ascii=False, default=str)
                    )

                    # colors_palette フィールドを特にチェック
                    if data and "outfit_items" in data:
                        for outfit_item in data["outfit_items"]:
                            clothing_item = outfit_item.get("clothing_item", {})
                            logger.info(f"Clothing item ID: {clothing_item.get('id')}")
                            logger.info(
                                f"colors_palette: {clothing_item.get('colors_palette')}"
                            )
                            logger.info(
                                f"colors_palette type: {type(clothing_item.get('colors_palette'))}"
                            )

                            # colors_palette の内容を詳しく調査
                            colors_palette = clothing_item.get("colors_palette")
                            if colors_palette:
                                logger.info(
                                    f"colors_palette content: {json.dumps(colors_palette, indent=2, ensure_ascii=False, default=str)}"
                                )

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    logger.error(f"Raw response: {response.text}")

            elif response.status_code == 500:
                logger.error("500 Internal Server Error detected!")
                logger.error(f"Response text: {response.text}")

                # HTMLエラーページの場合、詳細なエラー情報を抽出
                if "text/html" in response.headers.get("content-type", ""):
                    logger.error(
                        "HTML error page returned - this indicates a server-side exception"
                    )

                    # FastAPIのデバッグモードでスタックトレースが含まれている可能性
                    if "Traceback" in response.text:
                        logger.error("Server-side traceback found in response")

            else:
                logger.warning(f"Unexpected status code: {response.status_code}")
                logger.warning(f"Response: {response.text}")

    except httpx.ConnectError:
        logger.error("Cannot connect to API server. Is it running?")
        return False

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())
        return False

    return True


def test_clothing_items_endpoint(photo_id: str = "manual-2025-07-24"):
    """Clothing items エンドポイントもテスト."""
    url = f"{API_BASE_URL}/api/v2/outfits/photo/{photo_id}/clothing-items"

    try:
        logger.info(f"Testing clothing-items endpoint: {url}")

        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)

            logger.info(f"Clothing items status code: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.info("Clothing items response:")
                    for item in data:
                        logger.info(f"Item ID: {item.get('id')}")
                        logger.info(f"colors_palette: {item.get('colors_palette')}")

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error in clothing-items: {e}")

            elif response.status_code == 500:
                logger.error("500 error in clothing-items endpoint!")
                logger.error(f"Response: {response.text}")

    except Exception as e:
        logger.error(f"Error testing clothing-items endpoint: {e}")


def test_healthz():
    """API サーバーが動作しているか確認."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{API_BASE_URL}/healthz")
            logger.info(f"Health check: {response.status_code}")
            return response.status_code == 200

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False


def main():
    """メイン実行関数."""
    logger.info("=== outfit_api.py 500エラー デバッグスクリプト ===")

    # 1. ヘルスチェック
    if not test_healthz():
        logger.error("API server is not responding. Please start the server first.")
        sys.exit(1)

    # 2. outfit photo エンドポイントテスト
    logger.info("\n=== Testing outfit photo endpoint ===")
    test_outfit_photo_endpoint()

    # 3. clothing items エンドポイントテスト
    logger.info("\n=== Testing clothing items endpoint ===")
    test_clothing_items_endpoint()

    # 4. 複数の photo_id でテスト
    logger.info("\n=== Testing with multiple photo IDs ===")
    test_photo_ids = [
        "manual-2025-07-01",
        "manual-2025-07-02",
        "manual-2025-07-03",
        "manual-2025-07-24",
        "non-existent-photo",  # 存在しないIDもテスト
    ]

    for photo_id in test_photo_ids:
        logger.info(f"\nTesting photo_id: {photo_id}")
        test_outfit_photo_endpoint(photo_id)


if __name__ == "__main__":
    main()
