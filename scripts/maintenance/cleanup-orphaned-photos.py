#!/usr/bin/env python3
"""未保存写真の自動クリーニングスクリプト.

データベースに登録されていない古い写真ファイルを削除します。
カメラサービスが保存した写真のうち、ユーザーがキャンセルしたものを
一定期間後に自動削除して、ストレージ容量を節約します。

使用例:
    # デフォルト設定（7日間保持、実際に削除）
    python cleanup-orphaned-photos.py

    # 30日間保持
    python cleanup-orphaned-photos.py --retention-days 30

    # ドライラン（削除せずに確認のみ）
    python cleanup-orphaned-photos.py --dry-run

    # 詳細ログ出力
    python cleanup-orphaned-photos.py --verbose
"""

# ruff: noqa: E402

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Set, Tuple

# プロジェクトのルートディレクトリをパスに追加
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
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


def parse_photo_filename(filename: str) -> datetime | None:
    """写真ファイル名から撮影日時を解析する.

    Args:
        filename: ファイル名 (例: photo_20240101_123456.jpg)

    Returns:
        撮影日時（JST）、解析できない場合は None

    """
    # photo_YYYYMMDD_HHMMSS.jpg 形式のパターン
    pattern = r"photo_(\d{8})_(\d{6})\.jpg"
    match = re.match(pattern, filename)

    if not match:
        return None

    try:
        date_str = match.group(1)
        time_str = match.group(2)

        # 日時文字列を解析
        dt_str = f"{date_str}{time_str}"
        dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S")

        # JST として扱う
        return dt.replace(tzinfo=JST)
    except ValueError:
        return None


def get_camera_photos(photos_dir: Path) -> List[Tuple[Path, datetime]]:
    """カメラサービスの写真ディレクトリから写真ファイルを取得.

    Args:
        photos_dir: 写真ディレクトリのパス

    Returns:
        (ファイルパス, 撮影日時) のリスト

    """
    photos = []

    if not photos_dir.exists():
        logger.warning(f"写真ディレクトリが存在しません: {photos_dir}")
        return photos

    for file_path in photos_dir.glob("photo_*.jpg"):
        capture_time = parse_photo_filename(file_path.name)

        if capture_time:
            photos.append((file_path, capture_time))
        else:
            # ファイル名から日時を解析できない場合は、ファイルの更新時刻を使用
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=JST)
                photos.append((file_path, mtime))
                logger.debug(
                    f"ファイル名を解析できません。更新時刻を使用: {file_path.name}"
                )
            except OSError as e:
                logger.error(f"ファイル情報の取得に失敗: {file_path}, エラー: {e}")

    return photos


def get_db_photo_filenames(db_url: str) -> Set[str]:
    """データベースに登録されている写真ファイル名を取得.

    Args:
        db_url: データベース接続URL

    Returns:
        ファイル名のセット

    """
    engine = create_engine(db_url)

    with Session(engine) as session:
        # データベースから全ての写真のファイル名を取得
        stmt = select(Photo.filename).where(Photo.deleted_at.is_(None))
        results = session.execute(stmt).scalars().all()

        # ファイル名のセットを作成
        # UUID.jpg 形式と photo_YYYYMMDD_HHMMSS.jpg 形式の両方に対応
        filenames = set()
        for filename in results:
            if filename:
                filenames.add(filename)
                # photo_ プレフィックスのファイル名も追加
                if not filename.startswith("photo_"):
                    # UUID から元のファイル名を推測することはできないので、
                    # データベースに保存されているファイル名のみを使用
                    pass

        return filenames


def cleanup_orphaned_photos(
    photos_dir: Path,
    db_url: str,
    retention_days: int,
    dry_run: bool = False,
    verbose: bool = False,
) -> Tuple[int, int, int]:
    """未保存の古い写真を削除.

    Args:
        photos_dir: 写真ディレクトリのパス
        db_url: データベース接続URL
        retention_days: 保持日数
        dry_run: True の場合、実際には削除せずログ出力のみ
        verbose: 詳細ログを出力

    Returns:
        (検査したファイル数, 削除対象ファイル数, 削除したファイル数)

    """
    logger.info("写真クリーニングを開始します")
    logger.info(f"写真ディレクトリ: {photos_dir}")
    logger.info(f"保持期間: {retention_days}日")
    logger.info(f"モード: {'ドライラン' if dry_run else '実行'}")

    # 現在時刻（JST）
    now = datetime.now(JST)
    cutoff_date = now - timedelta(days=retention_days)

    # カメラの写真を取得
    camera_photos = get_camera_photos(photos_dir)
    total_files = len(camera_photos)
    logger.info(f"カメラディレクトリ内の写真数: {total_files}")

    # データベースの写真ファイル名を取得
    try:
        db_filenames = get_db_photo_filenames(db_url)
        logger.info(f"データベース内の写真数: {len(db_filenames)}")
    except Exception as e:
        logger.error(f"データベースへの接続に失敗しました: {e}")
        return total_files, 0, 0

    # 削除対象のファイルを特定
    files_to_delete = []

    for file_path, capture_time in camera_photos:
        # 保持期間内のファイルはスキップ
        if capture_time > cutoff_date:
            if verbose:
                logger.debug(f"保持期間内: {file_path.name} (撮影: {capture_time})")
            continue

        # データベースに存在するファイルはスキップ
        if file_path.name in db_filenames:
            if verbose:
                logger.debug(f"データベースに存在: {file_path.name}")
            continue

        # 削除対象
        files_to_delete.append((file_path, capture_time))
        logger.info(f"削除対象: {file_path.name} (撮影: {capture_time})")

    # 削除実行
    deleted_count = 0

    if files_to_delete:
        logger.info(f"削除対象ファイル数: {len(files_to_delete)}")

        if not dry_run:
            for file_path, _ in files_to_delete:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"削除しました: {file_path.name}")
                except Exception as e:
                    logger.error(f"削除に失敗しました: {file_path.name}, エラー: {e}")
        else:
            logger.info("ドライランモードのため、実際の削除は行いません")
            deleted_count = len(files_to_delete)  # ドライランでは削除予定数を返す
    else:
        logger.info("削除対象のファイルはありません")

    # サマリー
    logger.info("クリーニング完了:")
    logger.info(f"  検査したファイル数: {total_files}")
    logger.info(f"  削除対象ファイル数: {len(files_to_delete)}")
    logger.info(f"  削除したファイル数: {deleted_count}")

    return total_files, len(files_to_delete), deleted_count


def main():
    """メイン処理."""
    parser = argparse.ArgumentParser(
        description="未保存写真の自動クリーニング",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--photos-dir",
        type=str,
        default=os.getenv("PHOTOS_DIR", "./photos"),
        help="写真ディレクトリのパス（デフォルト: $PHOTOS_DIR または ./photos）",
    )

    parser.add_argument(
        "--retention-days",
        type=int,
        default=int(os.getenv("PHOTO_RETENTION_DAYS", "7")),
        help="写真の保持日数（デフォルト: $PHOTO_RETENTION_DAYS または 7）",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("CLEANUP_DRY_RUN", "false").lower() == "true",
        help="削除せずに対象ファイルを表示のみ",
    )

    parser.add_argument("--verbose", action="store_true", help="詳細ログを出力")

    args = parser.parse_args()

    # クリーニング機能が無効化されている場合
    if os.getenv("CLEANUP_ENABLED", "true").lower() == "false":
        logger.info("クリーニング機能は無効化されています（CLEANUP_ENABLED=false）")
        return

    # データベースURLの取得
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL が設定されていません")
        sys.exit(1)

    # 写真ディレクトリのパス
    photos_dir = Path(args.photos_dir).resolve()

    # クリーニング実行
    try:
        cleanup_orphaned_photos(
            photos_dir=photos_dir,
            db_url=db_url,
            retention_days=args.retention_days,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        logger.info("処理を中断しました")
        sys.exit(130)
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
