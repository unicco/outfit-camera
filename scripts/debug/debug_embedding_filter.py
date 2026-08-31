#!/usr/bin/env python3
"""Debug embedding filtering logic."""

# ruff: noqa: E402

import os
import sys

api_path = "./api"
sys.path.insert(0, api_path)
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://coordinate_user:coordinate_pass@localhost:5438/coordinate_db"
)

from app.wardrobe_models import ClothingCategory, ClothingItem, ClothingStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def main():
    engine = create_engine(os.environ["DATABASE_URL"])
    Session = sessionmaker(bind=engine)
    session = Session()

    correct_shirt_id = "796010f3-2f62-4b60-84c3-19790913550d"

    print("🔍 埋め込みフィルタリング調査")

    # Step 1: 候補取得（_get_wardrobe_candidates と同じロジック）
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

    print(f"\n1. 初期候補取得: {len(candidates)}件")

    # Step 2: 埋め込みフィルタリング（match_with_wardrobe_items と同じロジック）
    candidates_with_embeddings = []
    for c in candidates:
        # 実際のフィルタ条件: embedding_vector is not None and embedding_vector != 'null'
        if c.embedding_vector is not None and c.embedding_vector != "null":
            candidates_with_embeddings.append(c)

    print(f"2. 埋め込みフィルタ後: {len(candidates_with_embeddings)}件")

    # Step 3: 正解シャツの追跡
    correct_in_initial = any(str(c.id) == correct_shirt_id for c in candidates)
    correct_in_filtered = any(
        str(c.id) == correct_shirt_id for c in candidates_with_embeddings
    )

    print("\n🎯 正解シャツの追跡:")
    print(f"   初期候補に存在: {'✅' if correct_in_initial else '❌'}")
    print(f"   埋め込みフィルタ後に存在: {'✅' if correct_in_filtered else '❌'}")

    # Step 4: 正解シャツの詳細調査
    if correct_in_initial:
        correct_shirt = (
            session.query(ClothingItem)
            .filter(ClothingItem.id == correct_shirt_id)
            .first()
        )
        if correct_shirt:
            print("\n📋 正解シャツの詳細:")
            print(f"   ID: {correct_shirt.id}")
            print(f"   名前: {correct_shirt.name}")
            print(f"   カテゴリ: {correct_shirt.category}")
            print(f"   ステータス: {correct_shirt.status}")
            print(
                f"   embedding_vector is not None: {correct_shirt.embedding_vector is not None}"
            )

            if correct_shirt.embedding_vector is not None:
                print(
                    f"   embedding_vector type: {type(correct_shirt.embedding_vector)}"
                )
                print(
                    f'   embedding_vector != "null": {correct_shirt.embedding_vector != "null"}'
                )
                print(f"   embedding length: {len(correct_shirt.embedding_vector)}")
                print(
                    f"   フィルタ条件合格: {correct_shirt.embedding_vector is not None and correct_shirt.embedding_vector != 'null'}"
                )
            else:
                print("   ❌ embedding_vector is None")

    # Step 5: 埋め込み状況の全体統計
    print("\n📊 候補アイテムの埋め込み状況:")
    none_count = sum(1 for c in candidates if c.embedding_vector is None)
    null_str_count = sum(1 for c in candidates if c.embedding_vector == "null")
    valid_count = sum(
        1
        for c in candidates
        if c.embedding_vector is not None and c.embedding_vector != "null"
    )

    print(f"   embedding_vector is None: {none_count}件")
    print(f'   embedding_vector == "null": {null_str_count}件')
    print(f"   有効な埋め込み: {valid_count}件")
    print(
        f"   合計: {none_count + null_str_count + valid_count}件 (候補: {len(candidates)}件)"
    )

    session.close()


if __name__ == "__main__":
    main()
