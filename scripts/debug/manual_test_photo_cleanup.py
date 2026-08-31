#!/usr/bin/env python3
"""写真クリーニング機能の動作確認スクリプト.

実際のファイルシステムとデータベースを使用して、
cleanup-orphaned-photos.py の動作を確認します。

使用例:
    # ドライランで動作確認
    python manual_test_photo_cleanup.py

    # 実際に削除（注意！）
    python manual_test_photo_cleanup.py --actually-delete
"""

# ruff: noqa: E402

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Photo

# 環境変数の読み込み
load_dotenv()

# ロガーの設定

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# JST タイムゾーン
JST = timezone(timedelta(hours=9))


def check_photos_status():
    """現在の写真の状態を確認."""
    # 環境変数から設定を取得
    photos_dir = Path(os.getenv("PHOTOS_DIR", "./photos")).resolve()
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        logger.error("DATABASE_URL が設定されていません")
        return

    logger.info("=" * 60)
    logger.info("写真の状態確認")
    logger.info("=" * 60)

    # カメラディレクトリの写真を確認
    if photos_dir.exists():
        photo_files = list(photos_dir.glob("photo_*.jpg"))
        logger.info(f"カメラディレクトリ: {photos_dir}")
        logger.info(f"写真ファイル数: {len(photo_files)}")

        # 古いファイルを表示
        now = datetime.now(JST)
        old_files = []

        for photo_file in photo_files:
            # ファイルの更新時刻を取得
            mtime = datetime.fromtimestamp(photo_file.stat().st_mtime, tz=JST)
            age_days = (now - mtime).days

            if age_days > 7:
                old_files.append((photo_file, age_days))

        if old_files:
            logger.info(f"\n7日以上前の写真: {len(old_files)}件")
            for photo_file, age_days in sorted(
                old_files, key=lambda x: x[1], reverse=True
            )[:10]:
                logger.info(f"  - {photo_file.name} ({age_days}日前)")
        else:
            logger.info("\n7日以上前の写真はありません")
    else:
        logger.warning(f"写真ディレクトリが存在しません: {photos_dir}")

    # データベースの写真を確認
    try:
        engine = create_engine(db_url)
        with Session(engine) as session:
            db_count = session.query(Photo).filter(Photo.deleted_at.is_(None)).count()
            logger.info(f"\nデータベース内の写真数: {db_count}")

            # 最新の写真を表示
            recent_photos = (
                session.query(Photo)
                .filter(Photo.deleted_at.is_(None))
                .order_by(Photo.captured_at.desc())
                .limit(5)
                .all()
            )

            if recent_photos:
                logger.info("\n最新の保存済写真:")
                for photo in recent_photos:
                    logger.info(f"  - {photo.filename} (撮影: {photo.captured_at})")
    except Exception as e:
        logger.error(f"データベースへのアクセスに失敗: {e}")


def test_cleanup(actually_delete=False):
    """クリーニング機能をテスト実行."""
    logger.info("\n" + "=" * 60)
    logger.info("クリーニングテスト実行")
    logger.info("=" * 60)

    # クリーニングスクリプトを実行
    cleanup_script = (
        project_root / "scripts" / "maintenance" / "cleanup-orphaned-photos.py"
    )

    if not cleanup_script.exists():
        logger.error(f"クリーニングスクリプトが見つかりません: {cleanup_script}")
        return

    # コマンドを構築
    cmd_parts = [sys.executable, str(cleanup_script), "--verbose"]

    if not actually_delete:
        cmd_parts.append("--dry-run")
        logger.info("ドライランモードで実行します（実際の削除は行いません）")
    else:
        logger.warning("⚠️  実際にファイルを削除します！")

    # 実行
    import subprocess

    result = subprocess.run(cmd_parts, capture_output=True, text=True)

    if result.stdout:
        logger.info("\n出力:")
        for line in result.stdout.strip().split("\n"):
            logger.info(f"  {line}")

    if result.stderr:
        logger.error("\nエラー出力:")
        for line in result.stderr.strip().split("\n"):
            logger.error(f"  {line}")

    if result.returncode != 0:
        logger.error(
            f"\nクリーニングスクリプトがエラーで終了しました (code: {result.returncode})"
        )
    else:
        logger.info("\nクリーニングスクリプトが正常に完了しました")


def main():
    """メイン処理."""
    parser = argparse.ArgumentParser(description="写真クリーニング機能の動作確認")

    parser.add_argument(
        "--actually-delete",
        action="store_true",
        help="実際にファイルを削除する（注意！）",
    )

    parser.add_argument("--skip-status", action="store_true", help="状態確認をスキップ")

    args = parser.parse_args()

    try:
        # 現在の状態を確認
        if not args.skip_status:
            check_photos_status()

        # クリーニングテスト実行
        test_cleanup(actually_delete=args.actually_delete)

    except KeyboardInterrupt:
        logger.info("\n処理を中断しました")
    except Exception as e:
        logger.error(f"\nエラーが発生しました: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
