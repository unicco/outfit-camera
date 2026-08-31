#!/usr/bin/env python3
"""Debug similarity ranking to find why correct shirt is not in top 20."""

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
os.environ["JINA_API_KEY"] = os.getenv("JINA_API_KEY", "your_jina_api_key_here")

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

    print("🔍 類似度ランキング詳細調査")

    # Step 1: 検出されたアイテムの埋め込み生成（実際のAI検出と同じ）
    jina_service = JinaAPIService(api_key=os.environ["JINA_API_KEY"])

    # 検出されたアイテムをシミュレート（topカテゴリ）
    detected_description = "Detected top clothing item"

    # Jina APIで埋め込み生成
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
    print(f"✅ 検出アイテムの埋め込み生成成功: {len(detected_embedding)}次元")

    # Step 2: 候補取得
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

    # Step 3: 埋め込みフィルタ
    candidates_with_embeddings = [
        c
        for c in candidates
        if c.embedding_vector is not None and c.embedding_vector != "null"
    ]

    print(
        f"候補アイテム: 初期={len(candidates)}, 埋め込み有り={len(candidates_with_embeddings)}"
    )

    # Step 4: 全候補の類似度計算
    similarities = []

    for candidate in candidates_with_embeddings:
        try:
            wardrobe_embedding = parse_embedding_vector(candidate.embedding_vector)
            if wardrobe_embedding is None:
                continue

            similarity = cosine_similarity(detected_embedding, wardrobe_embedding)

            similarities.append(
                {
                    "id": str(candidate.id),
                    "name": candidate.name,
                    "brand": candidate.brand or "ノーブランド",
                    "category": candidate.category.value,
                    "similarity": float(similarity),
                    "is_correct": str(candidate.id) == correct_shirt_id,
                }
            )

        except Exception as e:
            print(f"類似度計算エラー: {candidate.name} - {e}")
            continue

    # Step 5: 類似度でソート
    similarities.sort(key=lambda x: x["similarity"], reverse=True)

    print("\n📊 類似度ランキング（上位30件）:")
    print(
        f"{'順位':>4} {'類似度':>8} {'正解':>4} {'名前':<20} {'ブランド':<15} {'カテゴリ'}"
    )
    print(f"{'-' * 80}")

    correct_rank = None

    for i, item in enumerate(similarities[:30], 1):
        marker = "🎯" if item["is_correct"] else "  "
        print(
            f"{i:>4} {item['similarity']:>8.4f} {marker:>4} {item['name']:<20} {item['brand']:<15} {item['category']}"
        )

        if item["is_correct"]:
            correct_rank = i

    print("\n🎯 正解シャツの結果:")
    if correct_rank:
        print(f"   順位: {correct_rank}位")
        correct_item = next(item for item in similarities if item["is_correct"])
        print(
            f"   類似度: {correct_item['similarity']:.4f} ({correct_item['similarity'] * 100:.1f}%)"
        )
        print(f"   20位以内: {'✅' if correct_rank <= 20 else '❌'}")

        if correct_rank > 20:
            print("   ❌ 20位以内に入らないため表示されません")
            print(f"   20位の類似度: {similarities[19]['similarity']:.4f}")
    else:
        print("   ❌ 正解シャツが類似度計算結果に含まれていません")

    print("\n📈 類似度分布統計:")
    sim_values = [item["similarity"] for item in similarities]
    if sim_values:
        print(f"   最高: {max(sim_values):.4f}")
        print(f"   最低: {min(sim_values):.4f}")
        print(f"   平均: {np.mean(sim_values):.4f}")
        print(f"   20位: {similarities[19]['similarity']:.4f} (表示境界)")

    session.close()


if __name__ == "__main__":
    main()
