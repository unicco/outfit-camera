#!/usr/bin/env python3
"""更新確認とフル表示スクリプト."""

import json
import os
import sys

# Add project root to path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

from app.database import get_db  # type: ignore[import-not-found]
from app.wardrobe_models import ClothingItem  # type: ignore[import-not-found]


def verify_update(item_id: str) -> None:
    """更新を確認してフル表示."""
    db = next(get_db())

    try:
        # アイテム取得
        item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
        if not item:
            print(f"❌ アイテムが見つかりません: {item_id}")
            return

        print("📋 アイテム情報 (更新後):")
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

        print("\n🔍 完全なimage_metadata:")
        if item.image_metadata:
            # 整形して表示
            print(
                json.dumps(
                    item.image_metadata, indent=2, ensure_ascii=False, default=str
                )
            )
        else:
            print("   なし")

        # Phase 2分析結果の有無を確認
        if item.image_metadata and "features" in item.image_metadata:
            features = item.image_metadata["features"]
            print("\n✅ Phase 2分析結果が見つかりました:")

            if "jina_analysis" in features:
                jina = features["jina_analysis"]
                print("   🤖 Jina分析:")
                print(f"      説明: {jina.get('description', 'N/A')}")
                print(f"      タスク: {jina.get('task_type', 'N/A')}")
                print(f"      次元: {jina.get('embedding_dimension', 'N/A')}")
                print(f"      日時: {jina.get('analysis_date', 'N/A')}")

            if "color_analysis" in features:
                color = features["color_analysis"]
                print("   🎨 色分析:")
                print(f"      支配的色: {color.get('dominant_colors', 'N/A')}")

            if "texture_analysis" in features:
                texture = features["texture_analysis"]
                print("   🧵 テクスチャ分析:")
                print(f"      素材: {texture.get('material', 'N/A')}")
                print(f"      パターン: {texture.get('pattern', 'N/A')}")
                print(f"      質感: {texture.get('texture', 'N/A')}")

            if "style_analysis" in features:
                style = features["style_analysis"]
                print("   👕 スタイル分析:")
                print(f"      サブカテゴリ: {style.get('subcategory', 'N/A')}")
                print(f"      スタイル: {style.get('style', 'N/A')}")
        else:
            print("\n❌ Phase 2分析結果が見つかりません")

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    item_id = "796010f3-2f62-4b60-84c3-19790913550d"

    print("🔍 更新確認とフル表示")
    print(f"📋 対象アイテムID: {item_id}")
    print("-" * 60)

    verify_update(item_id)
