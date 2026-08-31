#!/usr/bin/env python3
"""ワードローブデータ移行スクリプト.

ローカル環境のワードローブデータを本番環境に移行するためのスクリプト。
エクスポート、インポート、データ検証機能を提供。

Usage:
    # データをエクスポート
    python migrate_wardrobe_data.py export --output wardrobe_export.json

    # データをインポート
    python migrate_wardrobe_data.py import --input wardrobe_export.json --target-url http://pi-camera.local:8000

    # データ検証
    python migrate_wardrobe_data.py verify --source-url http://localhost:8000 --target-url http://pi-camera.local:8000
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, Optional

import httpx


class WardrobeMigrator:
    """ワードローブデータ移行クラス."""

    def __init__(
        self,
        source_url: str = "http://localhost:8000",
        target_url: Optional[str] = None,
    ):
        self.source_url = source_url.rstrip("/")
        self.target_url = target_url.rstrip("/") if target_url else None
        self.logger = logging.getLogger(__name__)

    async def export_data(
        self, output_file: str, include_images: bool = True
    ) -> Dict[str, Any]:
        """ローカル環境からワードローブデータをエクスポート.

        Args:
            output_file: 出力ファイルパス
            include_images: 画像情報を含めるか

        Returns:
            エクスポート結果

        """
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                # エクスポートAPIを呼び出し
                response = await client.post(
                    f"{self.source_url}/api/v2/wardrobe/export",
                    params={"include_images": include_images},
                )
                response.raise_for_status()

                export_data = response.json()

                # ファイルに保存
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)

                total_items = export_data.get("export_metadata", {}).get(
                    "total_items", 0
                )
                self.logger.info(
                    f"✅ Successfully exported {total_items} items to {output_file}"
                )

                return {
                    "success": True,
                    "file": output_file,
                    "total_items": total_items,
                    "file_size": os.path.getsize(output_file),
                }

        except httpx.RequestError as e:
            self.logger.error(f"❌ Network error during export: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Failed to export data: {e}")
            raise

    async def import_data(
        self, input_file: str, overwrite_existing: bool = False
    ) -> Dict[str, Any]:
        """本番環境にワードローブデータをインポート.

        Args:
            input_file: インポートファイルパス
            overwrite_existing: 既存データを上書きするか

        Returns:
            インポート結果

        """
        if not self.target_url:
            raise ValueError("Target URL is required for import operation")

        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                # ファイルをアップロード
                with open(input_file, "rb") as f:
                    files = {
                        "file": (os.path.basename(input_file), f, "application/json")
                    }
                    data = {"overwrite_existing": overwrite_existing}

                    response = await client.post(
                        f"{self.target_url}/api/v2/wardrobe/import", files=files, data=data
                    )
                    response.raise_for_status()

                import_result = response.json()
                stats = import_result.get("statistics", {})

                self.logger.info("✅ Import completed:")
                self.logger.info(f"   - Total items: {stats.get('total_items', 0)}")
                self.logger.info(f"   - Imported: {stats.get('imported', 0)}")
                self.logger.info(f"   - Skipped: {stats.get('skipped', 0)}")
                self.logger.info(f"   - Errors: {len(stats.get('errors', []))}")

                if stats.get("errors"):
                    self.logger.warning("⚠️ Import errors:")
                    for error in stats["errors"]:
                        self.logger.warning(f"   - {error}")

                return import_result

        except httpx.RequestError as e:
            self.logger.error(f"❌ Network error during import: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Failed to import data: {e}")
            raise

    async def verify_data(self) -> Dict[str, Any]:
        """ソースと対象環境のデータ整合性を検証.

        Returns:
            検証結果

        """
        if not self.target_url:
            raise ValueError("Target URL is required for verification")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # ソース環境の統計を取得
                source_response = await client.get(
                    f"{self.source_url}/api/v2/wardrobe/analytics/stats"
                )
                source_response.raise_for_status()
                source_stats = source_response.json()

                # 対象環境の統計を取得
                target_response = await client.get(
                    f"{self.target_url}/api/v2/wardrobe/analytics/stats"
                )
                target_response.raise_for_status()
                target_stats = target_response.json()

                # 統計比較
                source_total = source_stats.get("totalItems", 0)
                target_total = target_stats.get("totalItems", 0)

                verification_result = {
                    "source_stats": source_stats,
                    "target_stats": target_stats,
                    "comparison": {
                        "total_items_match": source_total == target_total,
                        "source_total": source_total,
                        "target_total": target_total,
                        "difference": target_total - source_total,
                    },
                }

                if source_total == target_total:
                    self.logger.info(
                        f"✅ Data verification passed: {source_total} items in both environments"
                    )
                else:
                    self.logger.warning(
                        f"⚠️ Data mismatch: Source={source_total}, Target={target_total}"
                    )

                return verification_result

        except httpx.RequestError as e:
            self.logger.error(f"❌ Network error during verification: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Failed to verify data: {e}")
            raise

    async def health_check(self, url: str) -> Dict[str, Any]:
        """指定URLのヘルスチェック.

        Args:
            url: チェック対象URL

        Returns:
            ヘルスチェック結果

        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{url}/healthz")
                response.raise_for_status()

                self.logger.info(f"✅ Health check passed: {url}")
                return {"success": True, "url": url, "status": response.status_code}

        except httpx.RequestError as e:
            self.logger.error(f"❌ Health check failed for {url}: {e}")
            return {"success": False, "url": url, "error": str(e)}
        except Exception as e:
            self.logger.error(f"❌ Health check error for {url}: {e}")
            return {"success": False, "url": url, "error": str(e)}


async def main():
    """メイン処理."""
    parser = argparse.ArgumentParser(description="ワードローブデータ移行スクリプト")
    subparsers = parser.add_subparsers(dest="command", help="実行コマンド")

    # エクスポートコマンド
    export_parser = subparsers.add_parser("export", help="データをエクスポートする")
    export_parser.add_argument("--output", "-o", required=True, help="出力ファイルパス")
    export_parser.add_argument(
        "--source-url", default="http://localhost:8000", help="ソースURL"
    )
    export_parser.add_argument(
        "--no-images", action="store_true", help="画像情報を除外"
    )

    # インポートコマンド
    import_parser = subparsers.add_parser("import", help="データをインポートする")
    import_parser.add_argument(
        "--input", "-i", required=True, help="インポートファイルパス"
    )
    import_parser.add_argument("--target-url", required=True, help="対象環境URL")
    import_parser.add_argument(
        "--overwrite", action="store_true", help="既存データを上書き"
    )

    # 検証コマンド
    verify_parser = subparsers.add_parser("verify", help="データを検証する")
    verify_parser.add_argument(
        "--source-url", default="http://localhost:8000", help="ソースURL"
    )
    verify_parser.add_argument("--target-url", required=True, help="対象環境URL")

    # ヘルスチェックコマンド
    health_parser = subparsers.add_parser("health", help="ヘルスチェック")
    health_parser.add_argument("--url", required=True, help="チェック対象URL")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # ログ設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    try:
        if args.command == "export":
            migrator = WardrobeMigrator(source_url=args.source_url)

            # ヘルスチェック
            health_result = await migrator.health_check(args.source_url)
            if not health_result["success"]:
                sys.exit(1)

            # エクスポート実行
            result = await migrator.export_data(
                args.output, include_images=not args.no_images
            )
            print(
                f"Export completed: {result['total_items']} items ({result['file_size']} bytes)"
            )

        elif args.command == "import":
            migrator = WardrobeMigrator(target_url=args.target_url)

            # ヘルスチェック
            health_result = await migrator.health_check(args.target_url)
            if not health_result["success"]:
                sys.exit(1)

            # インポート実行
            result = await migrator.import_data(args.input, args.overwrite)
            stats = result.get("statistics", {})
            print(
                f"Import completed: {stats.get('imported', 0)}/{stats.get('total_items', 0)} items"
            )

            if stats.get("errors"):
                print("Import errors occurred. Check logs for details.")
                sys.exit(1)

        elif args.command == "verify":
            migrator = WardrobeMigrator(
                source_url=args.source_url, target_url=args.target_url
            )

            # 両環境のヘルスチェック
            source_health = await migrator.health_check(args.source_url)
            target_health = await migrator.health_check(args.target_url)

            if not (source_health["success"] and target_health["success"]):
                sys.exit(1)

            # データ検証
            result = await migrator.verify_data()
            comparison = result["comparison"]

            if comparison["total_items_match"]:
                print(
                    f"✅ Verification passed: {comparison['source_total']} items in both environments"
                )
            else:
                print("⚠️ Data mismatch detected:")
                print(f"   Source: {comparison['source_total']} items")
                print(f"   Target: {comparison['target_total']} items")
                print(f"   Difference: {comparison['difference']}")
                sys.exit(1)

        elif args.command == "health":
            migrator = WardrobeMigrator()
            health_result = await migrator.health_check(args.url)

            if health_result["success"]:
                print(f"✅ Health check passed: {args.url}")
            else:
                print(
                    f"❌ Health check failed: {args.url} - {health_result.get('error', 'Unknown error')}"
                )
                sys.exit(1)

    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
