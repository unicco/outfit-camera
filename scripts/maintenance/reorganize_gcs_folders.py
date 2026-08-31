#!/usr/bin/env python3
"""GCS フォルダ構造整理スクリプト - Issue #557.

全身写真を example-wardrobe-dev/wardrobe/ から fullbody/YYYY-MM-DD/ に移動
ワードローブ写真は wardrobe/ フォルダに残す
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

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


def get_fullbody_photos() -> List[Tuple[str, str, str, str]]:
    """全身写真の情報を取得 (id, file_path, filename, captured_date)."""
    conn = get_database_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, file_path, filename, DATE(captured_at AT TIME ZONE 'Asia/Tokyo') as captured_date
            FROM photos
            WHERE source = 'upload'
            AND file_path LIKE 'https://storage.googleapis.com/example-wardrobe-dev/wardrobe/%'
            AND deleted_at IS NULL
            ORDER BY captured_at
        """
        )
        return cursor.fetchall()
    finally:
        conn.close()


def get_wardrobe_photos() -> List[Tuple[str, str]]:
    """ワードローブ写真の情報を取得 (id, image_urls)."""
    conn = get_database_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, image_urls
            FROM clothing_items
            WHERE image_urls IS NOT NULL
        """
        )
        return cursor.fetchall()
    finally:
        conn.close()


def copy_gcs_object(client: storage.Client, source_path: str, dest_path: str) -> bool:
    """GCS オブジェクトをコピー."""
    try:
        # URLからバケット名とオブジェクトパスを抽出
        if not source_path.startswith("https://storage.googleapis.com/"):
            return False

        path_parts = source_path.replace("https://storage.googleapis.com/", "").split(
            "/", 1
        )
        if len(path_parts) != 2:
            return False

        source_bucket_name, source_object_name = path_parts

        source_bucket = client.bucket(source_bucket_name)
        source_blob = source_bucket.blob(source_object_name)

        # コピー先のバケット名とオブジェクトパスを設定
        dest_bucket = client.bucket(source_bucket_name)  # 同じバケット内での移動
        dest_blob = dest_bucket.blob(dest_path)

        # オブジェクトが存在するか確認
        if not source_blob.exists():
            print(f"Warning: Source object not found: {source_path}")
            return False

        # コピー先が既に存在する場合はスキップ
        if dest_blob.exists():
            print(f"Destination already exists, skipping: {dest_path}")
            return True

        # コピー実行
        dest_blob.rewrite(source_blob)
        print(f"Copied: {source_object_name} -> {dest_path}")
        return True

    except Exception as e:
        print(f"Error copying {source_path} to {dest_path}: {e}")
        return False


def update_photo_path(cursor, photo_id: str, new_path: str) -> bool:
    """データベースの写真パスを更新（接続を再利用）."""
    try:
        cursor.execute(
            """
            UPDATE photos
            SET file_path = %s, updated_at = NOW()
            WHERE id = %s
        """,
            (new_path, photo_id),
        )
        return True
    except Exception as e:
        print(f"Error updating photo path for {photo_id}: {e}")
        return False


def reorganize_fullbody_photos(
    client: storage.Client, dry_run: bool = True
) -> Dict[str, int]:
    """全身写真をfullbody/YYYY-MM-DD/ 構造に整理."""
    results = {"success": 0, "failed": 0, "skipped": 0}

    print("=== 全身写真の整理を開始 ===")
    fullbody_photos = get_fullbody_photos()
    print(f"対象写真数: {len(fullbody_photos)}")

    if not fullbody_photos:
        print("対象の写真がありません")
        return results

    # データベース接続を1つ作成して再利用
    conn = None
    cursor = None

    if not dry_run:
        conn = get_database_connection()
        cursor = conn.cursor()

    try:
        for photo_id, file_path, filename, captured_date in tqdm(
            fullbody_photos, desc="全身写真整理中"
        ):
            try:
                # 新しいパスを生成
                # captured_date は 'YYYY-MM-DD' 形式
                new_object_path = f"fullbody/{captured_date}/{filename}"
                new_full_path = f"https://storage.googleapis.com/example-wardrobe-dev/{new_object_path}"

                if dry_run:
                    results["success"] += 1
                else:
                    # トランザクション制御: DB更新 → GCS操作 の順で実行
                    # まずDBを更新（ロールバック可能）
                    if update_photo_path(cursor, photo_id, new_full_path):
                        # GCS でファイルをコピー
                        if copy_gcs_object(client, file_path, new_object_path):
                            # トランザクションをコミット
                            conn.commit()
                            print(f"  ✅ 完了: {filename}")
                            results["success"] += 1
                        else:
                            # GCS コピー失敗時はDBをロールバック
                            conn.rollback()
                            print(f"  ❌ ファイルコピーエラー: {filename}")
                            results["failed"] += 1
                    else:
                        # DB更新失敗時はロールバック
                        conn.rollback()
                        print(f"  ❌ データベース更新エラー: {filename}")
                        results["failed"] += 1

            except Exception as e:
                if conn:
                    conn.rollback()
                print(f"  ❌ エラー: {filename} - {e}")
                results["failed"] += 1

    finally:
        if conn:
            conn.close()

    return results


def main():
    """メイン実行関数."""
    import argparse

    parser = argparse.ArgumentParser(description="GCS フォルダ構造整理")
    parser.add_argument(
        "--execute", action="store_true", help="実際に実行（デフォルトはdry-run）"
    )
    args = parser.parse_args()

    print("=== GCS フォルダ構造整理スクリプト ===")
    print(f"モード: {'実行' if args.execute else 'DRY RUN'}")

    # 環境設定
    setup_environment()

    try:
        # クライアント初期化
        client = get_gcs_client()

        # 全身写真の整理
        results = reorganize_fullbody_photos(client, dry_run=not args.execute)

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
