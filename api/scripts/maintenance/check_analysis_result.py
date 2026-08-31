#!/usr/bin/env python3
"""分析結果確認スクリプト."""

import json
import os
import sys

# Add project root to path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

from app.database import get_db  # type: ignore[import-not-found]
from app.wardrobe_models import ClothingItem  # type: ignore[import-not-found]


def check_analysis_result(item_id: str) -> None:
    """分析結果を確認."""
    db = next(get_db())

    try:
        # アイテム取得
        item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
        if not item:
            print(f"❌ アイテムが見つかりません: {item_id}")
            return

        print("📋 分析後のアイテム情報:")
        print(f"   ID: {item.id}")
        print(f"   名前: {item.name}")
        print(f"   カテゴリ: {item.category}")
        print(f"   サブカテゴリ: {item.subcategory}")
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

        print(f"   色パレット: {item.colors_palette}")
        print(f"   プライマリカラー: {primary_color}")
        print(f"   セカンダリカラー: {secondary_color}")
        print(f"   マテリアル: {item.material}")
        print(f"   パターン: {item.pattern}")
        print(f"   ブランド: {item.brand}")

        print("\n🔍 image_metadata内容:")
        if item.image_metadata:
            # JSON形式で整形表示
            formatted_metadata = json.dumps(
                item.image_metadata, indent=2, ensure_ascii=False
            )
            print(formatted_metadata)
        else:
            print("   なし")

        # Jina embeddingの確認
        print("\n📡 Jina Embedding情報:")
        print(
            f"   ベクトル次元: {len(item.embedding_vector) if item.embedding_vector else 'なし'}"
        )
        print(f"   モデルバージョン: {item.embedding_model_version}")
        print(f"   計算日時: {item.embedding_computed_at}")

        if item.embedding_vector and len(item.embedding_vector) >= 5:
            print(
                f"   ベクトル例: [{', '.join(map(str, item.embedding_vector[:5]))}...]"
            )

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    item_id = "796010f3-2f62-4b60-84c3-19790913550d"

    print("🔍 分析結果確認")
    print(f"📋 対象アイテムID: {item_id}")
    print("-" * 60)

    check_analysis_result(item_id)
