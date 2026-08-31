#!/usr/bin/env python3
"""ワードローブデータ移行機能のテストスクリプト.

Issue #531 の実装テスト用
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
from typing import Dict, Any

import httpx


class WardrobeMigrationTester:
    """ワードローブデータ移行テスト用クラス."""

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url.rstrip("/")
        self.logger = logging.getLogger(__name__)

    async def test_api_health(self) -> bool:
        """API のヘルスチェック."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.api_url}/healthz")
                response.raise_for_status()
                self.logger.info(f"✅ API health check passed: {self.api_url}")
                return True
        except Exception as e:
            self.logger.error(f"❌ API health check failed: {e}")
            return False

    async def test_export_endpoint(self) -> Dict[str, Any]:
        """エクスポート API のテスト."""
        self.logger.info("🧪 Testing export endpoint...")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # エクスポート実行
                response = await client.post(
                    f"{self.api_url}/api/v2/wardrobe/export",
                    params={"include_images": True},
                )
                response.raise_for_status()

                export_data = response.json()

                # データ構造の検証
                required_fields = ["export_metadata", "clothing_items"]
                for field in required_fields:
                    if field not in export_data:
                        raise ValueError(f"Missing required field: {field}")

                metadata = export_data["export_metadata"]
                clothing_items = export_data["clothing_items"]

                self.logger.info("✅ Export test passed:")
                self.logger.info(f"   - Total items: {metadata.get('total_items', 0)}")
                self.logger.info(
                    f"   - Exported at: {metadata.get('exported_at', 'N/A')}"
                )
                self.logger.info(
                    f"   - Include images: {metadata.get('include_images', False)}"
                )

                return {
                    "success": True,
                    "data": export_data,
                    "total_items": len(clothing_items),
                }

        except Exception as e:
            self.logger.error(f"❌ Export test failed: {e}")
            return {"success": False, "error": str(e)}

    async def test_import_endpoint(self, test_data: Dict[str, Any]) -> Dict[str, Any]:
        """インポート API のテスト."""
        self.logger.info("🧪 Testing import endpoint...")

        try:
            # テストデータを一時ファイルに保存
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(test_data, f, indent=2, ensure_ascii=False)
                temp_file = f.name

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    # インポート実行（上書きしない、テスト目的）
                    with open(temp_file, "rb") as f:
                        files = {
                            "file": (os.path.basename(temp_file), f, "application/json")
                        }
                        data = {"overwrite_existing": False}  # テスト時は上書きしない

                        response = await client.post(
                            f"{self.api_url}/api/v2/wardrobe/import",
                            files=files,
                            data=data,
                        )
                        response.raise_for_status()

                import_result = response.json()
                stats = import_result.get("statistics", {})

                self.logger.info("✅ Import test passed:")
                self.logger.info(f"   - Total items: {stats.get('total_items', 0)}")
                self.logger.info(f"   - Imported: {stats.get('imported', 0)}")
                self.logger.info(f"   - Skipped: {stats.get('skipped', 0)}")
                self.logger.info(f"   - Errors: {len(stats.get('errors', []))}")

                return {"success": True, "result": import_result}

            finally:
                # 一時ファイルを削除
                os.unlink(temp_file)

        except Exception as e:
            self.logger.error(f"❌ Import test failed: {e}")
            return {"success": False, "error": str(e)}

    async def test_wardrobe_stats(self) -> Dict[str, Any]:
        """ワードローブ統計 API のテスト."""
        self.logger.info("🧪 Testing wardrobe stats...")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_url}/api/v2/wardrobe/analytics/stats"
                )
                response.raise_for_status()

                stats = response.json()

                self.logger.info("✅ Stats test passed:")
                self.logger.info(f"   - Total items: {stats.get('totalItems', 0)}")
                self.logger.info(f"   - Categories: {len(stats.get('categories', {}))}")
                self.logger.info(
                    f"   - Recently added: {stats.get('recentlyAdded', 0)}"
                )

                return {"success": True, "stats": stats}

        except Exception as e:
            self.logger.error(f"❌ Stats test failed: {e}")
            return {"success": False, "error": str(e)}

    async def run_full_test(self) -> bool:
        """完全なテストスイートを実行."""
        self.logger.info("🚀 Starting full migration test suite...")

        # 1. ヘルスチェック
        if not await self.test_api_health():
            return False

        # 2. 統計取得テスト
        stats_result = await self.test_wardrobe_stats()
        if not stats_result["success"]:
            return False

        # 3. エクスポートテスト
        export_result = await self.test_export_endpoint()
        if not export_result["success"]:
            return False

        # 4. インポートテスト（エクスポートしたデータを使用）
        if export_result["total_items"] > 0:
            import_result = await self.test_import_endpoint(export_result["data"])
            if not import_result["success"]:
                return False
        else:
            self.logger.info("⏭️ Skipping import test (no data to test with)")

        self.logger.info("🎉 All tests passed!")
        return True


async def main():
    """メイン処理."""
    import argparse

    parser = argparse.ArgumentParser(description="ワードローブデータ移行機能テスト")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="APIサーバーURL"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細なログを表示")

    args = parser.parse_args()

    # ログ設定
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Testing migration APIs at: {args.api_url}")

    try:
        tester = WardrobeMigrationTester(api_url=args.api_url)
        success = await tester.run_full_test()

        if success:
            print("\n✅ すべてのテストが成功しました！")
            print("Issue #531 の実装が正常に動作しています。")
            sys.exit(0)
        else:
            print("\n❌ テストが失敗しました。")
            print("ログを確認して問題を修正してください。")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n❌ テストがユーザーによって中断されました")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
