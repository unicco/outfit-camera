#!/usr/bin/env python3
"""Jina API残りトークンでの一括分析可能性を推定."""

import os
import sys
from typing import Any, Dict, Optional

# Add project root and src/ to path
_project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, "src"))

from app.database import get_db  # noqa: E402  # type: ignore[import-not-found]
from app.wardrobe_models import (  # noqa: E402
    ClothingItem,
)  # type: ignore[import-not-found]


def estimate_jina_cost() -> Optional[Dict[str, Any]]:
    """Jina API残りトークンでの一括分析可能性を推定."""
    db = next(get_db())

    try:
        # 全アイテム取得
        items = db.query(ClothingItem).all()

        # Jina分析が必要なアイテムをカウント
        need_jina_analysis = 0
        jina_complete_items = []

        for item in items:
            has_jina = False
            if item.image_metadata and "features" in item.image_metadata:
                features = item.image_metadata["features"]
                if "jina_analysis" in features:
                    has_jina = True
                    jina_complete_items.append(item.name[:20])

            if not has_jina:
                need_jina_analysis += 1

        print("📊 Jina API 使用量推定")
        print("-" * 50)
        print(f"📋 総アイテム数: {len(items)}")
        print(f"✅ Jina分析済: {len(jina_complete_items)}")
        print(f"❌ Jina分析が必要: {need_jina_analysis}")

        if jina_complete_items:
            print("\n✅ 既に分析済のアイテム:")
            for name in jina_complete_items[:5]:
                print(f"   - {name}")
            if len(jina_complete_items) > 5:
                print(f"   ... 他 {len(jina_complete_items) - 5} 件")

        # Jina API使用統計を取得
        try:
            from coordinate_recorder.jina_api_service import JinaAPIService

            jina_api_key = os.getenv("JINA_API_KEY")

            if jina_api_key:
                jina_service = JinaAPIService(api_key=jina_api_key)
                usage_stats = jina_service.get_usage_stats()

                print("\n💰 現在のJina API使用状況:")
                if usage_stats:
                    # 使用統計の詳細表示
                    if hasattr(usage_stats, "__dict__"):
                        for key, value in usage_stats.__dict__.items():
                            print(f"   {key}: {value}")
                    elif isinstance(usage_stats, dict):
                        for key, value in usage_stats.items():
                            print(f"   {key}: {value}")
                    else:
                        print(f"   統計データ: {usage_stats}")
                else:
                    print("   統計データを取得できませんでした")

                # 概算コスト計算
                # Jina embeddings v4: マルチモーダル画像+テキスト
                # 一般的に1リクエスト = 1画像 = 約数百〜数千トークン
                estimated_tokens_per_item = 1000  # 保守的な推定
                total_estimated_tokens = need_jina_analysis * estimated_tokens_per_item

                print("\n🧮 必要トークン推定:")
                print(
                    f"   アイテム1件あたり: 約 {estimated_tokens_per_item:,} トークン"
                )
                print(
                    f"   総必要トークン: 約 {total_estimated_tokens:,} トークン ({need_jina_analysis} アイテム)"
                )

                # リスク評価
                if total_estimated_tokens < 100000:
                    risk_level = "🟢 低リスク"
                    recommendation = "実行を推奨"
                elif total_estimated_tokens < 500000:
                    risk_level = "🟡 中リスク"
                    recommendation = "注意して実行"
                else:
                    risk_level = "🔴 高リスク"
                    recommendation = "段階的実行を推奨"

                print(f"\n⚠️  リスク評価: {risk_level}")
                print(f"💡 推奨アクション: {recommendation}")

                # バッチサイズの提案
                if need_jina_analysis > 10:
                    batch_sizes = [5, 10, 20, need_jina_analysis]
                    print("\n📦 バッチ実行オプション:")
                    for batch_size in batch_sizes:
                        if batch_size > need_jina_analysis:
                            batch_size = need_jina_analysis
                        batches = (need_jina_analysis + batch_size - 1) // batch_size
                        tokens_per_batch = batch_size * estimated_tokens_per_item
                        print(
                            f"   バッチサイズ {batch_size:2}: {batches}回実行, 1回あたり約{tokens_per_batch:,}トークン"
                        )
                        if batch_size == need_jina_analysis:
                            break

            else:
                print("❌ JINA_API_KEYが設定されていません")

        except ImportError as e:
            print(f"❌ Jina APIサービスのインポートに失敗: {e}")
        except Exception as e:
            print(f"❌ Jina API統計取得エラー: {e}")

        return {
            "total_items": len(items),
            "need_analysis": need_jina_analysis,
            "estimated_tokens": need_jina_analysis * 1000,
        }

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        return None
    finally:
        db.close()


if __name__ == "__main__":
    print("🔍 Jina API トークン使用量推定")
    print("=" * 50)

    result = estimate_jina_cost()

    if result:
        print("=" * 50)
        need_analysis = result["need_analysis"]
        estimated_tokens = result["estimated_tokens"]

        if need_analysis == 0:
            print("🎉 全アイテムのJina分析が完了しています！")
        elif need_analysis <= 10:
            print(f"💡 少数アイテム({need_analysis}件)なので、一括実行が適しています")
        elif estimated_tokens <= 100000:
            print(f"💡 推定トークン数({estimated_tokens:,})は許容範囲内です")
        else:
            print(
                f"⚠️  推定トークン数({estimated_tokens:,})が多いため、バッチ実行を検討してください"
            )
