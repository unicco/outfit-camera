#!/usr/bin/env python3
"""Backfill 撮影写真の参加者（photos.attendees）.

撮影時にしか記録していない `photos.attendees`（その日
会った人）を、Google カレンダーの ICS フィードから過去にも遡って埋める。/today の
人別コーデ一覧を「これから蓄積」を待たずに動作確認できるようにする。

仕組み:
- `CALENDAR_ICS_URLS` の ICS フィードを全期間パースし `日付 → 参加者` マップを作る
  （app.services.calendar_ics.fetch_attendees_by_date）。
- 各 Photo の撮影日（JST）に対応する参加者を photos.attendees に書き込む。
- redaction は適用しない（保存するのは名前のみで「誰と会ったか」の記録のため）。

限界:
- ICS フィードの過去ウィンドウは限られる（Google の secret ICS は概ね直近〜数年）。
  さらに古いものは life-log DB（calendar 取り込み #136・別 VPS）にあるが当面は ICS 範囲。
- 当時タイトルに `@名前` を付けていない過去予定は復元不可。

べき等性:
- デフォルトは attendees 未設定（NULL）の写真だけ対象。--all で既存値も上書き。

使い方:
    python scripts/maintenance/backfill_photo_attendees.py            # 未設定の全写真
    python scripts/maintenance/backfill_photo_attendees.py --all      # 既存値も上書き
    python scripts/maintenance/backfill_photo_attendees.py --dry-run  # 件数だけ
"""

# ruff: noqa: E402

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to Python path（scripts/maintenance/ から 2 階層上）
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "api"))
sys.path.insert(0, str(project_root / "src"))

os.environ.setdefault("PYTHONPATH", str(project_root / "src"))

from app.database import SessionLocal
from app.models import Photo
from app.services.calendar_ics import fetch_attendees_by_date
from app.settings import get_settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def backfill(overwrite: bool = False, dry_run: bool = False) -> None:
    settings = get_settings()
    if not settings.calendar_ics_urls:
        logger.error("CALENDAR_ICS_URLS が未設定のため中止")
        return

    db = SessionLocal()
    try:
        query = db.query(Photo).filter(Photo.deleted_at.is_(None))
        if not overwrite:
            query = query.filter(Photo.attendees.is_(None))
        photos = query.all()

        if not photos:
            logger.info("対象写真なし（すべて埋まっている）")
            return

        # 撮影日(JST)の最小・最大で 1 回だけ ICS を取得する
        capture_dates = [p.captured_at.date() for p in photos if p.captured_at]
        if not capture_dates:
            logger.info("撮影日時のある写真がない（中止）")
            return
        start_date, end_date = min(capture_dates), max(capture_dates)
        logger.info(
            "対象 %d 件 / 期間 %s 〜 %s の参加者を ICS から取得",
            len(photos),
            start_date,
            end_date,
        )

        by_date = fetch_attendees_by_date(
            settings.calendar_ics_urls, start_date, end_date
        )
        if not by_date:
            logger.error("ICS から参加者を取得できなかった（中止）")
            return
        logger.info("ICS で参加者がいた日: %d 日", len(by_date))

        filled = 0
        missing = 0
        for photo in photos:
            if not photo.captured_at:
                continue
            key = photo.captured_at.date().isoformat()
            attendees = by_date.get(key)
            if not attendees:
                missing += 1
                continue
            photo.attendees = attendees
            filled += 1

        logger.info(
            "書き込み対象 %d 件 / 対応する予定なし %d 件",
            filled,
            missing,
        )

        if dry_run:
            logger.info("--dry-run のため commit せず終了")
            db.rollback()
            return

        db.commit()
        logger.info("✅ backfill 完了: %d 件を更新", filled)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill photo attendees from ICS")
    parser.add_argument(
        "--all",
        action="store_true",
        help="attendees が既にある写真も上書きする",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="書き込まず件数のみ表示する",
    )
    args = parser.parse_args()
    backfill(overwrite=args.all, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
