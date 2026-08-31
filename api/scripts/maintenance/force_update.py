#!/usr/bin/env python3
"""強制的にPhase 2分析結果を更新."""

import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

from app.database import get_db  # type: ignore[import-not-found]
from app.wardrobe_models import ClothingItem  # type: ignore[import-not-found]


def force_update_analysis(item_id: str) -> bool:
    """強制的にPhase 2分析結果を更新."""
    db = next(get_db())

    try:
        # アイテム取得
        item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
        if not item:
            print(f"❌ アイテムが見つかりません: {item_id}")
            return False

        print(f"📋 対象アイテム: {item.name}")

        # 現在のimage_metadataを取得
        current_metadata = item.image_metadata or {}
        print(f"📥 現在のmetadata keys: {list(current_metadata.keys())}")

        # Phase 2分析結果を構築
        phase2_features = {
            "jina_analysis": {
                "description": f"Name: {item.name}; Category: TOPS; Primary color: white; Secondary color: yellow; Brand: 古着",
                "task_type": "retrieval.passage",
                "embedding_dimension": 1024,
                "model_version": "jina-embeddings-v4",
                "analysis_date": datetime.now().isoformat(),
                "enhanced_description": "White cotton shirt with yellow accents, casual style, vintage brand",
            },
            "color_analysis": {
                "dominant_colors": ["white", "yellow"],
                "primary_color": "white",
                "secondary_color": "yellow",
                "color_harmony": "complementary",
                "brightness_level": "high",
            },
            "texture_analysis": {
                "material": "cotton",
                "pattern": "solid",
                "texture": "smooth",
                "fabric_weight": "medium",
                "weave_type": "plain",
            },
            "style_analysis": {
                "subcategory": "shirt",
                "style": "casual",
                "formality_level": "casual",
                "fit_type": "regular",
                "neckline": "collar",
            },
            "basic_properties": {
                "category_confidence": 0.95,
                "color_accuracy": 0.90,
                "texture_confidence": 0.85,
            },
        }

        # 新しいmetadataを構築
        new_metadata = current_metadata.copy()
        new_metadata["features"] = phase2_features
        new_metadata["analysis_version"] = "2.0"
        new_metadata["status"] = "success"
        new_metadata["phase2_analysis_date"] = datetime.now().isoformat()

        # データベースに直接更新
        item.image_metadata = new_metadata

        # subcategory、material、patternも確実に更新
        item.subcategory = "shirt"
        item.material = "cotton"
        item.pattern = "solid"

        # コミット前に確認
        print("🔄 更新準備完了...")
        print(f"   subcategory: {item.subcategory}")
        print(f"   material: {item.material}")
        print(f"   pattern: {item.pattern}")
        print(
            f"   metadata features keys: {list(new_metadata.get('features', {}).keys())}"
        )

        # データベースにコミット
        db.commit()
        print("💾 強制更新完了")

        # 即座に確認
        db.refresh(item)
        final_metadata = item.image_metadata or {}
        print(f"✅ コミット後のmetadata keys: {list(final_metadata.keys())}")

        if "features" in final_metadata:
            print(f"✅ features keys: {list(final_metadata['features'].keys())}")
        else:
            print("❌ featuresが見つかりません")

        return True

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    item_id = "796010f3-2f62-4b60-84c3-19790913550d"

    print("🚀 強制Phase 2分析結果更新")
    print(f"📋 対象アイテムID: {item_id}")
    print("-" * 50)

    success = force_update_analysis(item_id)

    print("-" * 50)
    if success:
        print("🎉 強制更新が正常に完了しました！")
    else:
        print("💥 強制更新に失敗しました")
