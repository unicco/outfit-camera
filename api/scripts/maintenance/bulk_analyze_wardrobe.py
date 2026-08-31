#!/usr/bin/env python3
"""ワードローブ全体に Phase 2 AI 分析を実行するスクリプト."""

import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# プロジェクトルートを Python パスに追加
project_root = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(project_root))

load_dotenv()
load_dotenv(".env.common")

# データベース設定
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://coordinate_user:coordinate_pass@localhost:5438/coordinate_db",
)

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# データベース接続設定
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_wardrobe_items() -> list[Any]:  # type: ignore[misc]
    """すべてのワードローブアイテムを取得."""
    from app.wardrobe_models import ClothingItem

    session = SessionLocal()
    try:
        items = (
            session.query(ClothingItem).filter(ClothingItem.status == "ACTIVE").all()
        )

        logger.info(f"📊 Found {len(items)} active wardrobe items")

        # Phase 2 分析済アイテムを確認
        analyzed_count = 0
        for item in items:  # type: ignore[unreachable]
            if item.image_metadata and isinstance(item.image_metadata, dict):  # type: ignore[unreachable]
                if (
                    "material_type" in item.image_metadata
                    or "texture_description" in item.image_metadata
                ):
                    analyzed_count += 1

        logger.info(f"🔬 {analyzed_count} items already have Phase 2 analysis")
        logger.info(f"⚡ {len(items) - analyzed_count} items need Phase 2 analysis")

        return items

    finally:
        session.close()


def analyze_wardrobe_item(item):
    """個別アイテムの Phase 2 分析を実行."""
    from app.wardrobe_ai_analyzer import WardrobeAIAnalyzer

    session = SessionLocal()
    try:
        # AI アナライザー初期化
        analyzer = WardrobeAIAnalyzer()

        # 画像パスを取得
        image_path = None
        if item.image_urls:
            if isinstance(item.image_urls, dict):
                image_path = item.image_urls.get("original")
            elif isinstance(item.image_urls, list) and len(item.image_urls) > 0:
                image_path = item.image_urls[0]

        if not image_path:
            logger.warning(f"⚠️ No image found for item {item.id}: {item.name}")
            return False

        # ローカルファイルパスに変換（必要に応じて）
        if image_path.startswith("/static/"):
            # ローカルファイルシステムのパス
            local_path = Path("wardrobe_images") / image_path.replace(
                "/static/wardrobe_images/", ""
            )
            if local_path.exists():
                image_path = str(local_path)
            else:
                logger.warning(f"⚠️ Image file not found: {local_path}")
                return False

        # アイテム情報を準備
        # colors_paletteから主色・副色を抽出
        primary_color = None
        secondary_color = None
        if item.colors_palette and isinstance(item.colors_palette, dict):
            palette = item.colors_palette.get("palette", [])
            if isinstance(palette, list) and len(palette) > 0:
                sorted_colors = sorted(palette, key=lambda x: x.get("position", 999))
                primary_color = (
                    sorted_colors[0].get("hex") if len(sorted_colors) > 0 else None
                )
                secondary_color = (
                    sorted_colors[1].get("hex") if len(sorted_colors) > 1 else None
                )

        item_info = {
            "id": item.id,
            "name": item.name,
            "category": (
                item.category.value
                if hasattr(item.category, "value")
                else str(item.category)
            ),
            "subcategory": item.subcategory,
            "colors_palette": item.colors_palette,
            "color_primary": primary_color,
            "color_secondary": secondary_color,
        }

        logger.info(f"🔬 Analyzing item {item.id}: {item.name}")

        # Phase 2 分析実行
        analysis_result = analyzer.analyze_wardrobe_item(image_path, item_info)

        if analysis_result.get("status") == "success":
            # 結果をデータベースに保存
            if not item.image_metadata:
                item.image_metadata = {}

            # Phase 2 分析結果をマージ
            item.image_metadata.update(analysis_result)

            # セッションをマークして更新
            session.add(item)
            session.commit()

            logger.info(f"✅ Successfully analyzed item {item.id}: {item.name}")
            return True
        else:
            error = analysis_result.get("error", "Unknown error")
            logger.error(f"❌ Failed to analyze item {item.id}: {error}")
            return False

    except Exception as e:
        logger.error(f"❌ Exception analyzing item {item.id}: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def main():
    """メイン実行関数."""
    logger.info("🚀 Starting bulk Phase 2 analysis for wardrobe items")

    # アイテム取得
    items = get_wardrobe_items()
    if not items:
        logger.info("📭 No items found to analyze")
        return

    # 分析実行
    success_count = 0
    failure_count = 0

    for i, item in enumerate(items, 1):
        logger.info(f"📊 Progress: {i}/{len(items)} - Processing {item.name}")

        # 既に分析済かチェック
        if item.image_metadata and isinstance(item.image_metadata, dict):
            if (
                "material_type" in item.image_metadata
                or "texture_description" in item.image_metadata
            ):
                logger.info(f"⏭️ Skipping already analyzed item: {item.name}")
                continue

        # 分析実行
        if analyze_wardrobe_item(item):
            success_count += 1
        else:
            failure_count += 1

    # 結果レポート
    logger.info("🎉 Bulk analysis completed!")
    logger.info(f"✅ Successfully analyzed: {success_count} items")
    logger.info(f"❌ Failed to analyze: {failure_count} items")
    logger.info(f"📊 Total processed: {success_count + failure_count} items")


if __name__ == "__main__":
    main()
