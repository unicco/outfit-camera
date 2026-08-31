#!/usr/bin/env python3
"""単一ワードローブアイテムのPhase 2分析スクリプト."""

import os
import sys

# Add project root to path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

from app.database import get_db  # type: ignore[import-not-found]
from app.wardrobe_ai_analyzer import WardrobeAIAnalyzer  # type: ignore[import-not-found]
from app.wardrobe_models import ClothingItem  # type: ignore[import-not-found]


def analyze_single_item(item_id: str) -> bool:
    """指定されたアイテムにPhase 2分析を実行."""
    # データベース接続
    db = next(get_db())

    try:
        # アイテム取得
        item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
        if not item:
            print(f"❌ アイテムが見つかりません: {item_id}")
            return False

        print("📋 分析対象アイテム:")
        print(f"   ID: {item.id}")
        print(f"   名前: {item.name}")
        print(f"   カテゴリ: {item.category}")
        print(f"   ブランド: {item.brand}")

        # 画像URLを取得
        if not item.image_urls:
            print("❌ 画像URLが見つかりません")
            return False

        # 最初の画像URLを取得
        if isinstance(item.image_urls, list) and len(item.image_urls) > 0:
            image_url = item.image_urls[0]
        elif isinstance(item.image_urls, dict) and "original" in item.image_urls:
            image_url = item.image_urls["original"]
        else:
            print(f"❌ 有効な画像URLが見つかりません: {item.image_urls}")
            return False

        print(f"🖼️ 画像URL: {image_url}")

        # WardrobeAIAnalyzer初期化
        analyzer = WardrobeAIAnalyzer()

        # アイテム情報を辞書形式に変換
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
            "id": str(item.id),
            "name": item.name,
            "category": item.category.value if item.category else None,
            "subcategory": item.subcategory,
            "colors_palette": item.colors_palette,
            "color_primary": primary_color,
            "color_secondary": secondary_color,
            "material": item.material,
            "pattern": item.pattern,
            "brand": item.brand,
        }

        print("🔄 Phase 2分析を開始...")

        # Phase 2分析実行
        analysis_result = analyzer.analyze_wardrobe_item(image_url, item_info)

        if analysis_result.get("status") == "success":
            print("✅ Phase 2分析が完了しました")

            # 結果をimage_metadataに統合
            if not item.image_metadata:
                item.image_metadata = {}
            item.image_metadata.update(analysis_result)

            # 分析結果から基本属性を更新
            features = analysis_result.get("features", {})

            # subcategoryの更新
            style_analysis = features.get("style_analysis", {})
            if style_analysis.get("subcategory") and not item.subcategory:
                item.subcategory = style_analysis["subcategory"]
                print(f"📝 subcategory更新: {item.subcategory}")

            # materialの更新
            texture_analysis = features.get("texture_analysis", {})
            if texture_analysis.get("material") and not item.material:
                item.material = texture_analysis["material"]
                print(f"📝 material更新: {item.material}")

            # patternの更新
            if texture_analysis.get("pattern") and not item.pattern:
                item.pattern = texture_analysis["pattern"]
                print(f"📝 pattern更新: {item.pattern}")

            # データベースに保存
            db.commit()
            print("💾 データベースに保存完了")

            # 分析結果の詳細表示
            print("\n📊 分析結果詳細:")
            if "jina_analysis" in features:
                jina = features["jina_analysis"]
                description = jina.get("description", "N/A")[:100]
                print(f"   Jina AI Description: {description}...")
                print(f"   Task Type: {jina.get('task_type', 'N/A')}")

            if "color_analysis" in features:
                color = features["color_analysis"]
                dominant_colors = color.get("dominant_colors", [])
                print(f"   Dominant Colors: {dominant_colors[:3]}")

            if texture_analysis:
                print(f"   Material: {texture_analysis.get('material', 'N/A')}")
                print(f"   Pattern: {texture_analysis.get('pattern', 'N/A')}")
                print(f"   Texture: {texture_analysis.get('texture', 'N/A')}")

            if style_analysis:
                print(f"   Style: {style_analysis.get('style', 'N/A')}")
                print(f"   Subcategory: {style_analysis.get('subcategory', 'N/A')}")

            return True

        else:
            error_msg = analysis_result.get("error", "Unknown error")
            print(f"❌ Phase 2分析に失敗: {error_msg}")
            return False

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    # 正解シャツのID
    item_id = "796010f3-2f62-4b60-84c3-19790913550d"

    print("🚀 単一アイテムPhase 2分析開始")
    print(f"📋 対象アイテムID: {item_id}")
    print("-" * 50)

    success = analyze_single_item(item_id)

    print("-" * 50)
    if success:
        print("🎉 Phase 2分析が正常に完了しました！")
    else:
        print("💥 Phase 2分析に失敗しました")
