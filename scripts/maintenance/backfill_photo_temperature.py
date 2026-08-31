#!/usr/bin/env python3
"""Backfill 撮影写真の気温（設定地点の日次気温）.

起床ブリーフ画面（Issue #424）で「今日の気温に近い過去の記録」を照合するため、
各 Photo の撮影日（JST）に対応する設定地点の日次気温を Open-Meteo Archive から
取得して temperature_max / temperature_min に書き込む。

- 無料・API キー不要。日付範囲を 1 リクエストでまとめて取得する。
- べき等: temperature_max が未設定の写真だけを対象にするので、再実行で
  直近分（ERA5 反映後）を順次埋められる。

使い方:
    python scripts/maintenance/backfill_photo_temperature.py            # 未設定の全写真
    python scripts/maintenance/backfill_photo_temperature.py --all      # 既存値も上書き
    python scripts/maintenance/backfill_photo_temperature.py --dry-run  # 件数だけ
"""

# ruff: noqa: E402

import argparse
import asyncio
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
from app.services.environment import WeatherArchiveService
from app.settings import get_settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def backfill(overwrite: bool = False, dry_run: bool = False) -> None:
    settings = get_settings()
    archive = WeatherArchiveService(settings)
    if not archive.enabled:
        logger.error("MORNING_LOCATION_LAT / MORNING_LOCATION_LON が未設定のため中止")
        return

    db = SessionLocal()
    try:
        query = db.query(Photo).filter(Photo.deleted_at.is_(None))
        if not overwrite:
            query = query.filter(Photo.temperature_max.is_(None))
        photos = query.all()

        if not photos:
            logger.info("対象写真なし（すべて埋まっている）")
            return

        # 撮影日(JST)の最小・最大で 1 回だけ取得する
        capture_dates = [p.captured_at.date() for p in photos if p.captured_at]
        start_date, end_date = min(capture_dates), max(capture_dates)
        logger.info(
            "対象 %d 件 / 期間 %s 〜 %s の設定地点気温を取得",
            len(photos),
            start_date,
            end_date,
        )

        temps = await archive.get_daily_temperatures(start_date, end_date)
        if not temps:
            logger.error("Open-Meteo から気温を取得できなかった（中止）")
            return

        filled = 0
        missing = 0
        for photo in photos:
            if not photo.captured_at:
                continue
            key = photo.captured_at.date().isoformat()
            entry = temps.get(key)
            if entry is None or entry[0] is None:
                missing += 1
                continue
            hi, lo = entry
            photo.temperature_max = hi
            photo.temperature_min = lo
            filled += 1

        logger.info(
            "書き込み対象 %d 件 / 気温未取得（直近 ERA5 未反映等）%d 件",
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
    parser = argparse.ArgumentParser(description="Backfill photo temperature")
    parser.add_argument(
        "--all",
        action="store_true",
        help="temperature_max が既にある写真も上書きする",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="書き込まず件数のみ表示する",
    )
    args = parser.parse_args()
    asyncio.run(backfill(overwrite=args.all, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
