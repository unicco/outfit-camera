#!/usr/bin/env python3
"""Debug why correct shirt is not appearing in similarity ranking."""

# ruff: noqa: E402

import os
import sys

import numpy as np

api_path = "./api"
sys.path.insert(0, api_path)
sys.path.insert(0, "./src")
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://coordinate_user:coordinate_pass@localhost:5438/coordinate_db"
)

from app.embedding_utils import cosine_similarity, parse_embedding_vector
from app.wardrobe_models import ClothingCategory, ClothingItem, ClothingStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from coordinate_recorder.jina_api_service import JinaAPIService


def main():
    engine = create_engine(os.environ["DATABASE_URL"])
    Session = sessionmaker(bind=engine)
    session = Session()

    correct_shirt_id = "796010f3-2f62-4b60-84c3-19790913550d"

    print("🔍 正解シャツの詳細デバッグ")

    # Step 1: 正解シャツの取得
    correct_shirt = (
        session.query(ClothingItem).filter(ClothingItem.id == correct_shirt_id).first()
    )

    if not correct_shirt:
        print(f"❌ 正解シャツが見つかりません: {correct_shirt_id}")
        return

    print(f"✅ 正解シャツ発見: {correct_shirt.name} ({correct_shirt.brand})")
    print(f"   カテゴリ: {correct_shirt.category}")
    print(f"   ステータス: {correct_shirt.status}")

    # Step 2: 埋め込み詳細
    if correct_shirt.embedding_vector:
        print(f"   埋め込み存在: ✅ ({len(correct_shirt.embedding_vector)}次元)")

        # 埋め込みをパース
        try:
            parsed_embedding = parse_embedding_vector(correct_shirt.embedding_vector)
            if parsed_embedding is not None:
                print(f"   パース成功: ✅ ({len(parsed_embedding)}次元)")
                print(
                    f"   埋め込み統計: min={np.min(parsed_embedding):.4f}, max={np.max(parsed_embedding):.4f}, mean={np.mean(parsed_embedding):.4f}"
                )
            else:
                print("   ❌ パース失敗: None が返却")
                return
        except Exception as e:
            print(f"   ❌ パースエラー: {e}")
            return
    else:
        print("   埋め込み存在: ❌")
        return

    # Step 3: 検出アイテムの埋め込み生成
    print("\n🔄 検出アイテムの埋め込み生成")

    jina_service = JinaAPIService(api_key=os.environ["JINA_API_KEY"])

    detected_description = "Detected top clothing item"

    from PIL import Image

    placeholder_image = Image.new("RGB", (100, 100), color="white")
    result = jina_service.generate_embedding(
        placeholder_image,
        text=detected_description,
        use_cache=True,
        task="retrieval.query",
    )

    if not result.success:
        print(f"❌ 検出アイテムの埋め込み生成失敗: {result.error_message}")
        return

    detected_embedding = result.embedding
    print(f"✅ 検出アイテム埋め込み: {len(detected_embedding)}次元")

    # Step 4: 類似度計算
    print("\n🧮 類似度計算")

    try:
        similarity = cosine_similarity(detected_embedding, parsed_embedding)
        print(f"✅ 類似度計算成功: {similarity:.6f} ({similarity * 100:.2f}%)")

        # Step 5: 他のアイテムとの比較
        print("\n📊 他のアイテムとの比較（上位5件）")

        target_categories = [ClothingCategory.TOPS, ClothingCategory.OUTERWEAR]

        candidates = (
            session.query(ClothingItem)
            .filter(
                ClothingItem.category.in_(target_categories),
                ClothingItem.status == ClothingStatus.ACTIVE,
            )
            .limit(50)
            .all()
        )

        similarities = []

        for candidate in candidates:
            if (
                candidate.embedding_vector is not None
                and candidate.embedding_vector != "null"
            ):
                try:
                    wardrobe_embedding = parse_embedding_vector(
                        candidate.embedding_vector
                    )
                    if wardrobe_embedding is not None:
                        sim = cosine_similarity(detected_embedding, wardrobe_embedding)
                        similarities.append(
                            {
                                "id": str(candidate.id),
                                "name": candidate.name,
                                "brand": candidate.brand or "ノーブランド",
                                "similarity": float(sim),
                                "is_correct": str(candidate.id) == correct_shirt_id,
                            }
                        )
                except Exception as e:
                    print(f"   類似度計算エラー: {candidate.name} - {e}")
                    continue

        # ソート
        similarities.sort(key=lambda x: x["similarity"], reverse=True)

        print(f"{'順位':>4} {'類似度':>8} {'正解':>4} {'名前':<20} {'ブランド':<15}")
        print("-" * 65)

        correct_rank = None
        for i, item in enumerate(similarities[:10], 1):
            marker = "🎯" if item["is_correct"] else "  "
            print(
                f"{i:>4} {item['similarity']:>8.6f} {marker:>4} {item['name']:<20} {item['brand']:<15}"
            )

            if item["is_correct"]:
                correct_rank = i

        if correct_rank:
            print(f"\n🎯 正解シャツの順位: {correct_rank}位")
        else:
            # 正解シャツを探す
            for i, item in enumerate(similarities, 1):
                if item["is_correct"]:
                    print(
                        f"\n🎯 正解シャツの順位: {i}位 (類似度: {item['similarity']:.6f})"
                    )
                    break
            else:
                print(f"\n❌ 正解シャツが見つかりません（全{len(similarities)}件中）")

    except Exception as e:
        print(f"❌ 類似度計算でエラー: {e}")
        import traceback

        traceback.print_exc()

    session.close()


if __name__ == "__main__":
    main()
