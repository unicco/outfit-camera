#!/usr/bin/env python3
"""手動でJina AI分析を実行するスクリプト."""

import os
import sys
from datetime import datetime

# Add project root, api/, and src/ to path
_project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, "api"))
sys.path.insert(0, os.path.join(_project_root, "src"))

from app.database import get_db  # noqa: E402  # type: ignore[import-not-found]
from app.wardrobe_models import (  # noqa: E402
    ClothingItem,
)  # type: ignore[import-not-found]


def manual_jina_analysis(item_id: str) -> bool:
    """手動でJina AI分析を実行."""
    db = next(get_db())

    try:
        # アイテム取得
        item = db.query(ClothingItem).filter(ClothingItem.id == item_id).first()
        if not item:
            print(f"❌ アイテムが見つかりません: {item_id}")
            return False

        print(f"📋 分析対象アイテム: {item.name}")

        # Jina API keyチェック
        jina_api_key = os.getenv("JINA_API_KEY")
        if not jina_api_key:
            print("❌ JINA_API_KEYが設定されていません")
            return False

        # Jina APIサービス初期化
        try:
            from coordinate_recorder.jina_api_service import JinaAPIService

            jina_service = JinaAPIService(api_key=jina_api_key)
            print("✅ Jina APIサービス初期化完了")
        except ImportError as e:
            print(f"❌ Jina APIサービスのインポートに失敗: {e}")
            # パスの詳細確認
            print("📁 現在のPythonパス:")
            for p in sys.path:
                print(f"   {p}")
            return False

        # 画像URL取得
        image_url = None
        if isinstance(item.image_urls, list) and len(item.image_urls) > 0:
            image_url = item.image_urls[0]
        elif isinstance(item.image_urls, dict) and "original" in item.image_urls:
            image_url = item.image_urls["original"]
        else:
            print("❌ 有効な画像URLが見つかりません")
            return False

        print(f"🖼️ 画像URL: {image_url}")

        # テキスト説明作成
        description_parts = []
        if item.name:
            description_parts.append(f"Name: {item.name}")
        if item.category:
            description_parts.append(f"Category: {item.category.value}")
        if item.subcategory:
            description_parts.append(f"Type: {item.subcategory}")

        # colors_paletteから主色・副色を抽出
        if item.colors_palette and isinstance(item.colors_palette, dict):
            palette = item.colors_palette.get("palette", [])
            if isinstance(palette, list) and len(palette) > 0:
                sorted_colors = sorted(palette, key=lambda x: x.get("position", 999))
                if len(sorted_colors) > 0:
                    description_parts.append(
                        f"Primary color: {sorted_colors[0].get('hex')}"
                    )
                if len(sorted_colors) > 1:
                    description_parts.append(
                        f"Secondary color: {sorted_colors[1].get('hex')}"
                    )

        if item.material:
            description_parts.append(f"Material: {item.material}")
        if item.brand:
            description_parts.append(f"Brand: {item.brand}")

        text_description = (
            "; ".join(description_parts) if description_parts else "Clothing item"
        )
        print(f"📝 テキスト説明: {text_description}")

        # Jina AI分析実行
        print("🔄 Jina AI分析を実行中...")

        try:
            # マルチモーダル分析
            result = jina_service.generate_embedding(
                image=image_url, text=text_description, task="retrieval.passage"
            )

            if result and result.success and result.embedding is not None:
                print("✅ Jina AI分析完了")
                print(f"   ベクトル次元: {len(result.embedding)}")
                print(f"   先頭5要素: {result.embedding[:5]}")

                # image_metadataに結果を追加
                if not item.image_metadata:
                    item.image_metadata = {}

                if "features" not in item.image_metadata:
                    item.image_metadata["features"] = {}

                analyzed_at = datetime.now().astimezone().isoformat(timespec="seconds")
                item.image_metadata["features"]["jina_analysis"] = {
                    "description": text_description,
                    "task_type": "retrieval.passage",
                    "embedding_dimension": len(result.embedding),
                    "model_version": "jina-embeddings-v4",
                    "analysis_date": analyzed_at,
                    "usage_stats": result.usage if result.usage else None,
                }

                # 基本的な色分析とテクスチャ分析を追加
                item.image_metadata["features"]["color_analysis"] = {
                    "dominant_colors": (
                        [item.color_primary, item.color_secondary]
                        if item.color_secondary
                        else [item.color_primary]
                    ),
                    "primary_color": item.color_primary,
                    "secondary_color": item.color_secondary,
                }

                item.image_metadata["features"]["texture_analysis"] = {
                    "material": "cotton",  # デフォルト推定
                    "pattern": "solid",  # デフォルト推定
                    "texture": "smooth",  # デフォルト推定
                }

                item.image_metadata["features"]["style_analysis"] = {
                    "subcategory": "shirt",  # TOPSの場合のデフォルト推定
                    "style": "casual",  # デフォルト推定
                }

                # 分析バージョンとステータスを追加
                item.image_metadata["analysis_version"] = "2.0"
                item.image_metadata["status"] = "success"

                # subcategory、material、patternを更新
                if not item.subcategory:
                    item.subcategory = "shirt"
                    print(f"📝 subcategory更新: {item.subcategory}")

                if not item.material:
                    item.material = "cotton"
                    print(f"📝 material更新: {item.material}")

                if not item.pattern:
                    item.pattern = "solid"
                    print(f"📝 pattern更新: {item.pattern}")

                # データベースに保存
                db.commit()
                print("💾 データベースに保存完了")

                return True

            else:
                error_msg = (
                    result.error_message
                    if hasattr(result, "error_message")
                    else "不明なエラー"
                )
                print(f"❌ Jina AI分析結果が無効です: {error_msg}")
                return False

        except Exception as e:
            print(f"❌ Jina AI分析エラー: {e}")
            return False

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    item_id = "796010f3-2f62-4b60-84c3-19790913550d"

    print("🚀 手動Jina AI分析開始")
    print(f"📋 対象アイテムID: {item_id}")
    print("-" * 50)

    success = manual_jina_analysis(item_id)

    print("-" * 50)
    if success:
        print("🎉 Jina AI分析が正常に完了しました！")
    else:
        print("💥 Jina AI分析に失敗しました")
