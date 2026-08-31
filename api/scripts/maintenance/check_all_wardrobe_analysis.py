#!/usr/bin/env python3
"""全ワードローブアイテムのPhase 2分析状況を確認."""

import os
import sys

# Add project root to path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

from typing import Any
from app.database import get_db  # type: ignore[import-not-found]
from app.wardrobe_models import ClothingItem  # type: ignore[import-not-found]


def check_all_wardrobe_analysis() -> dict[str, Any]:
    """全ワードローブアイテムのPhase 2分析状況を確認."""
    db = next(get_db())

    try:
        # 全アイテム取得
        items = db.query(ClothingItem).all()

        print("📊 全ワードローブアイテム分析状況")
        print(f"📋 総アイテム数: {len(items)}")
        print("-" * 80)

        # 分析状況の統計
        total_items = len(items)
        has_phase2_features = 0
        has_subcategory = 0
        has_material = 0
        has_pattern = 0
        has_jina_analysis = 0

        # カテゴリ別の統計
        category_stats = {}

        for item in items:
            # カテゴリ別統計
            category = item.category.value if item.category else "UNKNOWN"
            if category not in category_stats:
                category_stats[category] = {
                    "total": 0,
                    "has_phase2": 0,
                    "has_subcategory": 0,
                    "has_material": 0,
                    "has_pattern": 0,
                }

            category_stats[category]["total"] += 1

            # Phase 2分析の有無をチェック
            has_features = False
            if item.image_metadata and "features" in item.image_metadata:
                has_features = True
                has_phase2_features += 1
                category_stats[category]["has_phase2"] += 1

                features = item.image_metadata["features"]
                if "jina_analysis" in features:
                    has_jina_analysis += 1

            # 基本属性の有無をチェック
            if item.subcategory:
                has_subcategory += 1
                category_stats[category]["has_subcategory"] += 1

            if item.material:
                has_material += 1
                category_stats[category]["has_material"] += 1

            if item.pattern:
                has_pattern += 1
                category_stats[category]["has_pattern"] += 1

            # 詳細表示（最初の10件と問題のあるアイテム）
            if len([i for i in items if i == item]) <= 10 or not has_features:
                status = "✅" if has_features else "❌"
                print(
                    f"{status} {item.name[:20]:20} | {category:8} | sub:{item.subcategory or 'None':10} | mat:{item.material or 'None':8} | pat:{item.pattern or 'None':8}"
                )

        print("-" * 80)
        print("📈 全体統計:")
        print(
            f"   Phase 2分析済: {has_phase2_features:3}/{total_items:3} ({has_phase2_features / total_items * 100:5.1f}%)"
        )
        print(
            f"   Jina分析済:    {has_jina_analysis:3}/{total_items:3} ({has_jina_analysis / total_items * 100:5.1f}%)"
        )
        print(
            f"   subcategory有り: {has_subcategory:3}/{total_items:3} ({has_subcategory / total_items * 100:5.1f}%)"
        )
        print(
            f"   material有り:    {has_material:3}/{total_items:3} ({has_material / total_items * 100:5.1f}%)"
        )
        print(
            f"   pattern有り:     {has_pattern:3}/{total_items:3} ({has_pattern / total_items * 100:5.1f}%)"
        )

        print("\n📊 カテゴリ別統計:")
        for category, stats in category_stats.items():
            total = stats["total"]
            phase2_rate = stats["has_phase2"] / total * 100 if total > 0 else 0
            sub_rate = stats["has_subcategory"] / total * 100 if total > 0 else 0
            mat_rate = stats["has_material"] / total * 100 if total > 0 else 0
            pat_rate = stats["has_pattern"] / total * 100 if total > 0 else 0

            print(
                f"   {category:12} | 総数:{total:2} | Phase2:{stats['has_phase2']:2}({phase2_rate:4.0f}%) | sub:{stats['has_subcategory']:2}({sub_rate:4.0f}%) | mat:{stats['has_material']:2}({mat_rate:4.0f}%) | pat:{stats['has_pattern']:2}({pat_rate:4.0f}%)"
            )

        # Phase 2分析が不完全なアイテムをリストアップ
        incomplete_items = []
        for item in items:
            if not (item.image_metadata and "features" in item.image_metadata):
                incomplete_items.append(item)

        if incomplete_items:
            print(f"\n❌ Phase 2分析が未完了のアイテム ({len(incomplete_items)}件):")
            for item in incomplete_items[:20]:  # 最初の20件のみ表示
                print(
                    f"   ID: {item.id} | {item.name[:30]:30} | {item.category.value if item.category else 'None':8}"
                )

            if len(incomplete_items) > 20:
                print(f"   ... 他 {len(incomplete_items) - 20} 件")

        return {
            "total_items": total_items,
            "phase2_complete": has_phase2_features,
            "incomplete_items": len(incomplete_items),
            "category_stats": category_stats,
        }

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        return {}
    finally:
        db.close()


if __name__ == "__main__":
    print("🔍 全ワードローブアイテムのPhase 2分析状況確認")
    print("=" * 80)

    stats = check_all_wardrobe_analysis()

    if stats:
        print("=" * 80)
        completion_rate = stats["phase2_complete"] / stats["total_items"] * 100
        if completion_rate < 80:
            print(f"⚠️  Phase 2分析完了率が低いです: {completion_rate:.1f}%")
            print(f"   未完了アイテム: {stats['incomplete_items']}件")
        else:
            print(f"✅ Phase 2分析がほぼ完了しています: {completion_rate:.1f}%")
