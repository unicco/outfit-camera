#!/usr/bin/env python3
"""GCS に原本の無い写真レコードに deleted_at を立てる.

起床ブリーフ（/today・HA push）の hero 写真は DB から気温の近い記録を選ぶだけで、
GCS に原本があるかを見ない。原本の無いレコードが残っていると画像が 404 になり、
毎朝の画面が壊れる。原本は復旧できない（soft delete 7 日・バージョニング無効）ので、
レコード側を論理削除して選定対象から外す。

物理削除ではなく deleted_at を立てるのは、outfit 記録との FK を壊さず、判定を
誤っても戻せるようにするため。

安全弁: GCS の一覧が空なら中止し、対象が全体の --max-ratio を超えたら --force
なしでは中止する。exists() 相当の個別確認ではなく一覧との突き合わせにしているのは、
GCS 側の一時障害を「全件が消えた」と誤読して全消しするのを防ぐため。

⚠️ GCS へのアップロードに失敗してローカル保存へ倒れた写真（upload.py のフォールバック）
も「原本なし」に見える。必ず --dry-run で対象を確かめてから実行する。

使い方:
    python scripts/maintenance/purge_photos_missing_in_gcs.py --dry-run  # 対象を表示
    python scripts/maintenance/purge_photos_missing_in_gcs.py            # 実行
"""

# ruff: noqa: E402

import argparse
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to Python path（scripts/maintenance/ から 2 階層上）
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "api"))
sys.path.insert(0, str(project_root / "src"))

os.environ.setdefault("PYTHONPATH", str(project_root / "src"))

from sqlalchemy.orm import load_only

from app.database import SessionLocal
from app.models import Photo
from app.storage.gcs_storage import GCSStorageHandler
from app.storage.storage_factory import get_storage_handler

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

_PHOTO_PREFIX = "photos/"
_PHOTO_SUFFIX = ".jpg"


def list_stored_photo_ids(handler: GCSStorageHandler) -> set[str]:
    """GCS の photos/ 配下にある写真 ID の集合を返す."""
    blobs = handler.client.list_blobs(handler.bucket_name, prefix=_PHOTO_PREFIX)
    return {
        blob.name[len(_PHOTO_PREFIX) : -len(_PHOTO_SUFFIX)]
        for blob in blobs
        if blob.name.endswith(_PHOTO_SUFFIX)
    }


def purge(dry_run: bool = False, max_ratio: float = 0.5, force: bool = False) -> int:
    """原本の無い写真を論理削除し、対象件数を返す."""
    handler = get_storage_handler()
    if not isinstance(handler, GCSStorageHandler):
        logger.error(
            "STORAGE_TYPE=gcs でないため中止（handler=%s）", type(handler).__name__
        )
        return 0

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        # load_only で必要な列だけ読む（embedding_vector 等の巨大 JSON を全件ぶん
        # デシリアライズすると数秒かかるため・morning_brief と同じ理由）
        photos = (
            db.query(Photo)
            .options(load_only(Photo.id, Photo.captured_at, Photo.deleted_at))
            .filter(Photo.deleted_at.is_(None))
            .all()
        )

        # GCS の一覧は DB を読んだ「後」に取る。逆順だと、その間に保存された写真が
        # どちらのスナップショットにも入らず「原本なし」に化けて消える。保存は GCS へ
        # 上げてから DB に登録する順なので（upload.py）、この順なら取りこぼさない
        stored = list_stored_photo_ids(handler)
        if not stored:
            logger.error(
                "GCS の %s 配下が空だった（GCS 障害の疑い・中止）", _PHOTO_PREFIX
            )
            return 0
        logger.info("GCS に原本がある写真: %d 件", len(stored))

        missing = [p for p in photos if str(p.id) not in stored]
        logger.info(
            "DB の有効な写真: %d 件 / 原本なし: %d 件", len(photos), len(missing)
        )

        if not missing:
            logger.info("対象なし（すべて原本がある）")
            return 0

        # 中止する場合も何が対象だったかは見せる（調査に使うため）
        for photo in sorted(missing, key=lambda p: p.captured_at or now):
            logger.info(
                "  %s（撮影 %s）",
                photo.id,
                photo.captured_at.date() if photo.captured_at else "不明",
            )

        ratio = len(missing) / len(photos)
        if ratio > max_ratio and not force:
            logger.error(
                "原本なしが %.1f%% と多すぎる（上限 %.1f%%）。"
                "GCS の設定ずれを疑う。意図的なら --force を付ける",
                ratio * 100,
                max_ratio * 100,
            )
            return 0

        if dry_run:
            logger.info("--dry-run のため commit せず終了")
            return len(missing)

        for photo in missing:
            photo.deleted_at = now
        db.commit()
        logger.info("✅ %d 件を論理削除した", len(missing))
        return len(missing)
    finally:
        db.close()


def ratio_arg(value: str) -> float:
    """--max-ratio を 0〜1 の有限な数に限る.

    nan を通すと `ratio > max_ratio` が常に偽になり、--force を付けずに全件を
    消せてしまう（安全弁が黙って消える）。
    """
    ratio = float(value)
    if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
        raise argparse.ArgumentTypeError(f"0〜1 の数値を指定してください: {value}")
    return ratio


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge photos missing in GCS")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="書き込まず対象を表示する",
    )
    parser.add_argument(
        "--max-ratio",
        type=ratio_arg,
        default=0.5,
        help="この比率を超えて原本なしなら中止する（既定 0.5）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="--max-ratio を超えても実行する",
    )
    args = parser.parse_args()
    purge(dry_run=args.dry_run, max_ratio=args.max_ratio, force=args.force)


if __name__ == "__main__":
    main()
