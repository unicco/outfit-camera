#!/usr/bin/env python3
"""既存アイテムの colors_palette を埋める（一度きりの backfill）.

扱いは 3 通り:
- eyedropper / manual（人が手で決めた） → 触らない
- auto_kmeans（既に物撮りから取った）   → 触らない（再実行しても済んだ分は飛ばす）
- それ以外（VLM・色なし）               → 物撮り写真から抽出して入れる

VLM が付けた色（vlm_color_hex）も残さず取り直す。実測では 35 件すべてが
CSS の名前付きカラー（#000000 が 13 件・#FFFFFF が 4 件・#D3D3D3 …）で、
実物を測った値ではなかった。明度の材料にすると 0% と 100% に張り付く。

VPS で実行する:
    PYTHONPATH=~/services/coordinate-recorder/api \
      ~/services/coordinate-recorder/.venv/bin/python \
      ~/services/coordinate-recorder/api/scripts/maintenance/backfill_item_colors.py --apply

--apply を付けるまで DB は変更しない。
"""

import argparse
import logging
import os
import sys
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.services import item_color  # noqa: E402
from app.upload_limits import MAX_IMAGE_UPLOAD_BYTES  # noqa: E402
from app.url_safety import is_allowed_storage_url  # noqa: E402
from app.wardrobe_models import ClothingItem  # noqa: E402

load_dotenv()
load_dotenv(".env.common")

# 既定値は置かない。接続先も認証情報も .env（VPS では自動で読まれる）から取る
DATABASE_URL = os.getenv("DATABASE_URL")
DOWNLOAD_TIMEOUT = 30

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _photo_url(item: ClothingItem) -> Optional[str]:
    """物撮り写真の URL を取り出す.

    image_urls は dict と配列の 2 つの形があり、routers/wardrobe.py の画像プロキシと
    同じ扱い方に揃える（本番 111 件は全部 dict だが、モデルの型は両方を許している）。
    """
    image_urls = item.image_urls
    if isinstance(image_urls, dict):
        original = image_urls.get("original")
    elif isinstance(image_urls, list) and image_urls:
        original = image_urls[0]
    else:
        return None
    return original if isinstance(original, str) and original else None


def should_extract(colors_palette: Optional[Dict[str, Any]]) -> bool:
    """物撮りから取り直す対象か.

    飛ばすのは 2 つだけ:
    - 人が決めた色（eyedropper / manual）
    - 既に物撮りから取った色（auto_kmeans）＝ 再実行しても済んだ分は触らない

    VLM が書いたものは palette 形式でも中身が CSS 定数なので取り直す。
    """
    if item_color.is_manually_set(colors_palette):
        return False
    if not isinstance(colors_palette, dict):
        return True
    if colors_palette.get("extraction_method") != item_color.METHOD_AUTO:
        return True
    return not colors_palette.get("palette")


def _fetch(url: str) -> bytes:
    # 自分のバケットの GCS URL 以外は取りに行かない（API 側の画像取得と同じ扱い）
    if not is_allowed_storage_url(url):
        raise ValueError(f"許可されていない画像 URL: {url}")

    # content を一括で受けると上限が効かないので、アップロードと同じ上限まで読む
    with requests.get(
        url, timeout=DOWNLOAD_TIMEOUT, allow_redirects=False, stream=True
    ) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            total += len(chunk)
            if total > MAX_IMAGE_UPLOAD_BYTES:
                raise ValueError(
                    f"画像が大きすぎる（{MAX_IMAGE_UPLOAD_BYTES} 超）: {url}"
                )
            chunks.append(chunk)
    return b"".join(chunks)


def backfill(apply_changes: bool) -> None:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL が設定されていない")

    engine = create_engine(DATABASE_URL)
    session = sessionmaker(bind=engine)()

    counts = {
        "manual": 0,
        "already": 0,
        "extracted": 0,
        "no_photo": 0,
        "failed": 0,
    }

    try:
        items = session.query(ClothingItem).all()
        logger.info("対象 %d 件（apply=%s）", len(items), apply_changes)

        for item in items:
            palette: Optional[Dict[str, Any]] = item.colors_palette

            if not should_extract(palette):
                if item_color.is_manually_set(palette):
                    counts["manual"] += 1
                else:
                    counts["already"] += 1
                continue

            url = _photo_url(item)
            if not url:
                counts["no_photo"] += 1
                logger.warning("写真が無い %s (%s)", item.id, item.name)
                continue

            try:
                extracted = item_color.extract_palette(_fetch(url))
            except Exception as e:
                counts["failed"] += 1
                logger.error("抽出に失敗 %s (%s): %s", item.id, item.name, e)
                continue

            counts["extracted"] += 1
            logger.info(
                "抽出 %s (%s) → %s [%s]",
                item.id,
                item.name,
                extracted["palette"][0]["hex"],
                extracted["mask_method"],
            )
            if apply_changes:
                item.colors_palette = extracted
                session.commit()

        if not apply_changes:
            logger.info("dry-run のため DB は変更していない（--apply で書き込む）")

        logger.info(
            "手動 %d / 既に palette %d / 抽出 %d / 写真なし %d / 失敗 %d",
            counts["manual"],
            counts["already"],
            counts["extracted"],
            counts["no_photo"],
            counts["failed"],
        )
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="DB に書き込む（既定は dry-run）"
    )
    args = parser.parse_args()
    backfill(args.apply)


if __name__ == "__main__":
    main()
