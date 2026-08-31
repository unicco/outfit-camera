#!/usr/bin/env python3
"""ワードローブ写真の本番環境移行スクリプト - Issue #557.

example-wardrobe-dev から example-wardrobe-prod にワードローブ写真をコピー
データベースの写真パスも更新
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Union

import psycopg
from google.cloud import storage
from tqdm import tqdm


def setup_environment():
    """環境変数とPythonパスを設定."""
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(project_root / "src"))
    sys.path.insert(0, str(project_root / "api"))

    # .envから環境変数を読み込み
    try:
        from dotenv import load_dotenv

        env_common_path = project_root / ".env.common"
        if env_common_path.exists():
            load_dotenv(env_common_path)
        env_path = project_root / ".env"
        load_dotenv(env_path, override=True)
    except ImportError:
        pass


def get_database_connection():
    """データベース接続を取得."""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://coordinate_user:coordinate_pass@localhost:5438/coordinate_db",
    )
    pg_url = database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(pg_url)


def get_gcs_client():
    """GCS クライアントを初期化."""
    gcs_project_id = os.getenv("GCS_PROJECT_ID")
    if not gcs_project_id:
        raise ValueError("GCS_PROJECT_ID environment variable is required")

    return storage.Client(project=gcs_project_id)


def get_wardrobe_items() -> List[Tuple[str, str, Union[str, Dict]]]:
    """ワードローブアイテムの情報を取得 (id, name, image_urls)."""
    conn = get_database_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, image_urls
            FROM clothing_items
            WHERE image_urls IS NOT NULL
            AND status = 'ACTIVE'
            ORDER BY created_at
        """
        )
        return cursor.fetchall()
    finally:
        conn.close()


def copy_gcs_object_cross_bucket(
    client: storage.Client,
    source_url: str,
    dest_bucket_name: str,
    dest_object_path: str,
) -> bool:
    """GCS オブジェクトを別バケットにコピー."""
    try:
        # URLからバケット名とオブジェクトパスを抽出
        if not source_url.startswith("https://storage.googleapis.com/"):
            return False

        path_parts = source_url.replace("https://storage.googleapis.com/", "").split(
            "/", 1
        )
        if len(path_parts) != 2:
            return False

        source_bucket_name, source_object_name = path_parts

        source_bucket = client.bucket(source_bucket_name)
        source_blob = source_bucket.blob(source_object_name)

        dest_bucket = client.bucket(dest_bucket_name)
        dest_blob = dest_bucket.blob(dest_object_path)

        # オブジェクトが存在するか確認
        if not source_blob.exists():
            print(f"Warning: Source object not found: {source_url}")
            return False

        # コピー先が既に存在する場合はスキップ
        if dest_blob.exists():
            print(f"Destination already exists, skipping: {dest_object_path}")
            return True

        # コピー実行
        dest_blob.rewrite(source_blob)
        print(f"Copied: {source_object_name} -> {dest_bucket_name}/{dest_object_path}")
        return True

    except Exception as e:
        print(
            f"Error copying {source_url} to {dest_bucket_name}/{dest_object_path}: {e}"
        )
        return False


def migrate_image_urls(image_urls_data) -> Dict:
    """image_urls を本番環境用に変換."""
    try:
        if isinstance(image_urls_data, str):
            image_urls = json.loads(image_urls_data)
        else:
            image_urls = image_urls_data
        new_image_urls = {}

        # original URL の変換
        if "original" in image_urls:
            original_url = image_urls["original"]
            new_original = original_url.replace(
                "example-wardrobe-dev", "example-wardrobe-prod"
            )
            new_image_urls["original"] = new_original

        # thumbnails URL の変換
        if "thumbnails" in image_urls:
            new_thumbnails = {}
            for thumb_key, thumb_url in image_urls["thumbnails"].items():
                new_thumb_url = thumb_url.replace(
                    "example-wardrobe-dev", "example-wardrobe-prod"
                )
                new_thumbnails[thumb_key] = new_thumb_url
            new_image_urls["thumbnails"] = new_thumbnails

        return new_image_urls

    except Exception as e:
        print(f"Error migrating image URLs: {e}")
        return {}


def update_clothing_item_urls(cursor, item_id: str, new_image_urls: Dict) -> bool:
    """データベースのワードローブアイテム画像URLを更新（接続を再利用）."""
    try:
        cursor.execute(
            """
            UPDATE clothing_items
            SET image_urls = %s, updated_at = NOW()
            WHERE id = %s
        """,
            (json.dumps(new_image_urls), item_id),
        )
        return True
    except Exception as e:
        print(f"Error updating clothing item URLs for {item_id}: {e}")
        return False


def migrate_wardrobe_to_prod(
    client: storage.Client, dry_run: bool = True
) -> Dict[str, int]:
    """ワードローブ写真を本番環境に移行."""
    results = {"success": 0, "failed": 0, "skipped": 0}

    print("=== ワードローブ写真の本番環境移行を開始 ===")
    wardrobe_items = get_wardrobe_items()
    print(f"対象アイテム数: {len(wardrobe_items)}")

    if not wardrobe_items:
        print("対象のアイテムがありません")
        return results

    # データベース接続を1つ作成して再利用
    conn = None
    cursor = None

    if not dry_run:
        conn = get_database_connection()
        cursor = conn.cursor()

    try:
        for item_id, name, image_urls_json in tqdm(
            wardrobe_items, desc="ワードローブ移行中"
        ):
            try:
                # image_urls をパース（既にdictの場合はそのまま使用）
                if isinstance(image_urls_json, str):
                    image_urls = json.loads(image_urls_json)
                elif isinstance(image_urls_json, dict):
                    image_urls = image_urls_json
                elif isinstance(image_urls_json, list):
                    print(f"  Warning: image_urls is list format, skipping {name}")
                    results["skipped"] += 1
                    continue
                else:
                    print(
                        f"  Warning: Unexpected image_urls format for {name}: {type(image_urls_json)}"
                    )
                    results["failed"] += 1
                    continue

                # コピーする画像URL一覧を取得
                urls_to_copy = []
                if "original" in image_urls:
                    urls_to_copy.append(image_urls["original"])
                if "thumbnails" in image_urls:
                    urls_to_copy.extend(image_urls["thumbnails"].values())

                if dry_run:
                    # 新しいURLを生成
                    new_image_urls = migrate_image_urls(image_urls)
                    results["success"] += 1
                else:
                    # トランザクション制御: DB更新 → GCS操作 の順で実行
                    # 新しいURLを生成
                    new_image_urls = migrate_image_urls(image_urls)

                    # まずDBを更新（ロールバック可能）
                    if update_clothing_item_urls(cursor, item_id, new_image_urls):
                        # 各画像をコピー
                        all_copied = True
                        for url in urls_to_copy:
                            # 元のオブジェクトパスを取得
                            path_parts = url.replace(
                                "https://storage.googleapis.com/example-wardrobe-dev/",
                                "",
                            )
                            dest_object_path = path_parts

                            if not copy_gcs_object_cross_bucket(
                                client,
                                url,
                                "example-wardrobe-prod",
                                dest_object_path,
                            ):
                                all_copied = False
                                break

                        if all_copied:
                            # トランザクションをコミット
                            conn.commit()
                            print(f"  ✅ 完了: {name}")
                            results["success"] += 1
                        else:
                            # GCS コピー失敗時はDBをロールバック
                            conn.rollback()
                            print(f"  ❌ ファイルコピーエラー: {name}")
                            results["failed"] += 1
                    else:
                        # DB更新失敗時はロールバック
                        conn.rollback()
                        print(f"  ❌ データベース更新エラー: {name}")
                        results["failed"] += 1

            except Exception as e:
                if conn:
                    conn.rollback()
                print(f"  ❌ エラー: {name} - {e}")
                results["failed"] += 1

    finally:
        if conn:
            conn.close()

    return results


def verify_prod_bucket_exists(client: storage.Client) -> bool:
    """本番バケットが存在するか確認."""
    try:
        bucket = client.bucket("example-wardrobe-prod")
        bucket.reload()
        return True
    except Exception as e:
        print(
            f"本番バケット 'example-wardrobe-prod' が存在しないか、アクセスできません: {e}"
        )
        return False


def main():
    """メイン実行関数."""
    import argparse

    parser = argparse.ArgumentParser(description="ワードローブ写真の本番環境移行")
    parser.add_argument(
        "--execute", action="store_true", help="実際に実行（デフォルトはdry-run）"
    )
    parser.add_argument(
        "--create-bucket",
        action="store_true",
        help="本番バケットが存在しない場合は作成",
    )
    args = parser.parse_args()

    print("=== ワードローブ写真本番環境移行スクリプト ===")
    print(f"モード: {'実行' if args.execute else 'DRY RUN'}")

    # 環境設定
    setup_environment()

    try:
        # クライアント初期化
        client = get_gcs_client()

        # 本番バケット存在確認
        if not verify_prod_bucket_exists(client):
            if args.create_bucket and not args.execute:
                print("注意: --create-bucket は --execute と併用してください")
                return
            elif args.create_bucket and args.execute:
                print("本番バケットを作成中...")
                bucket = client.bucket("example-wardrobe-prod")
                bucket = client.create_bucket(bucket, location="US")
                print(f"バケット '{bucket.name}' を作成しました")
            else:
                print(
                    "エラー: 本番バケットが存在しません。--create-bucket オプションを使用してください"
                )
                return

        # ワードローブ写真の移行
        results = migrate_wardrobe_to_prod(client, dry_run=not args.execute)

        print("\n=== 結果 ===")
        print(f"成功: {results['success']}")
        print(f"失敗: {results['failed']}")
        print(f"スキップ: {results['skipped']}")

        if not args.execute:
            print(
                "\n注意: これはDRY RUNです。実際に実行するには --execute を使用してください。"
            )

    except Exception as e:
        print(f"❌ エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
