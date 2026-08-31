#!/usr/bin/env python3
"""Hard negative mining script for improving embedding model."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from app import wardrobe_models  # noqa: F401  # Ensure clothing models are registered
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker

from app.search_log_models import SearchResultItem
from app.search_log_service import SearchLogService
from app.embedding_utils import parse_embedding_vector


class HardNegativeMiner:
    """ハードネガティブマイニングを実行するクラス."""

    def __init__(self, session):
        self.session = session
        self.search_log_service = SearchLogService(session)

    def collect_hard_negatives(
        self,
        days_back: int = 7,
        min_similarity: float = 0.5,
        max_rank: int = 10,
        min_rank: int = 2,
    ) -> List[Dict[str, Any]]:
        """ハードネガティブを収集.

        Args:
            days_back: 何日前までのログを対象とするか
            min_similarity: 最小類似度閾値（これ以上類似しているが間違っている）
            max_rank: 最大ランク
            min_rank: 最小ランク（1位は除外することが多い）

        Returns:
            ハードネガティブのリスト

        """
        hard_negatives = self.search_log_service.get_hard_negatives(
            days_back=days_back, min_similarity=min_similarity, max_rank=max_rank
        )

        # min_rank でフィルタ
        if min_rank > 1:
            hard_negatives = [hn for hn in hard_negatives if hn["rank"] >= min_rank]

        # 追加情報を取得
        enriched_negatives = []
        for hn in hard_negatives:
            # 正解アイテムを見つける
            correct_item = self._find_correct_item(hn["search_log_id"])

            if correct_item:
                hn["correct_item_id"] = correct_item["item_id"]
                hn["correct_item_name"] = correct_item["name"]
                hn["correct_item_embedding"] = correct_item["embedding"]
                enriched_negatives.append(hn)

        return enriched_negatives

    def _find_correct_item(self, search_log_id: str) -> Optional[Dict[str, Any]]:
        """検索ログから正解アイテムを見つける."""
        search_result = (
            self.session.query(SearchResultItem)
            .filter(
                and_(
                    SearchResultItem.search_log_id == search_log_id,
                    SearchResultItem.is_correct.is_(True),
                )
            )
            .first()
        )

        if search_result:
            wardrobe_item = search_result.wardrobe_item
            return {
                "item_id": str(wardrobe_item.id),
                "name": wardrobe_item.name,
                "category": wardrobe_item.category.value,
                "embedding": wardrobe_item.embedding_vector,
            }
        return None

    def create_triplets(
        self, hard_negatives: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """ハードネガティブからトリプレット（アンカー、ポジティブ、ネガティブ）を作成.

        Returns:
            トリプレットのリスト

        """
        triplets = []

        for hn in hard_negatives:
            if "correct_item_embedding" not in hn:
                continue

            # アンカー：検出されたアイテムの埋め込み
            anchor_embedding = hn.get("detected_embedding")
            if not anchor_embedding:
                continue

            # ポジティブ：正解アイテムの埋め込み
            positive_embedding = parse_embedding_vector(hn["correct_item_embedding"])
            if positive_embedding is None:
                continue

            # ネガティブ：誤認識されたアイテムの埋め込み
            negative_embedding = parse_embedding_vector(hn["negative_embedding"])
            if negative_embedding is None:
                continue

            triplet = {
                "anchor": {
                    "id": hn["detected_item_id"],
                    "description": hn["detected_description"],
                    "category": hn["detected_category"],
                    "embedding": anchor_embedding,
                },
                "positive": {
                    "id": hn["correct_item_id"],
                    "name": hn["correct_item_name"],
                    "embedding": positive_embedding.tolist(),
                },
                "negative": {
                    "id": hn["negative_item_id"],
                    "name": hn["negative_item_name"],
                    "category": hn["negative_item_category"],
                    "embedding": negative_embedding.tolist(),
                    "similarity": hn["similarity"],
                    "rank": hn["rank"],
                },
                "metadata": {
                    "search_log_id": hn["search_log_id"],
                    "timestamp": hn["timestamp"],
                    "similarity_gap": hn["similarity"]
                    - 0.0,  # Assuming correct item has higher similarity
                },
            }

            triplets.append(triplet)

        return triplets

    def save_hard_negatives(
        self, hard_negatives: List[Dict[str, Any]], output_path: str
    ):
        """ハードネガティブをファイルに保存."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 既存のデータを読み込む
        existing_data = []
        if output_file.exists():
            with open(output_file, "r") as f:
                existing_data = json.load(f)

        # 新しいデータを追加（重複チェック）
        existing_ids = {
            (d["search_log_id"], d["negative_item_id"]) for d in existing_data
        }

        new_data = []
        for hn in hard_negatives:
            key = (hn["search_log_id"], hn["negative_item_id"])
            if key not in existing_ids:
                new_data.append(hn)

        # 保存
        all_data = existing_data + new_data
        with open(output_file, "w") as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False, default=str)

        return len(new_data)

    def analyze_hard_negatives(
        self, hard_negatives: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """ハードネガティブを分析."""
        analysis = {
            "total_count": len(hard_negatives),
            "category_distribution": {},
            "similarity_distribution": {
                "0.5-0.6": 0,
                "0.6-0.7": 0,
                "0.7-0.8": 0,
                "0.8-0.9": 0,
                "0.9-1.0": 0,
            },
            "rank_distribution": {},
            "top_confused_pairs": [],
        }

        # カテゴリ分布
        for hn in hard_negatives:
            detected_cat = hn["detected_category"]
            negative_cat = hn["negative_item_category"]

            pair = f"{detected_cat} -> {negative_cat}"
            if pair not in analysis["category_distribution"]:
                analysis["category_distribution"][pair] = 0
            analysis["category_distribution"][pair] += 1

        # 類似度分布
        for hn in hard_negatives:
            sim = hn["similarity"]
            if 0.5 <= sim < 0.6:
                analysis["similarity_distribution"]["0.5-0.6"] += 1
            elif 0.6 <= sim < 0.7:
                analysis["similarity_distribution"]["0.6-0.7"] += 1
            elif 0.7 <= sim < 0.8:
                analysis["similarity_distribution"]["0.7-0.8"] += 1
            elif 0.8 <= sim < 0.9:
                analysis["similarity_distribution"]["0.8-0.9"] += 1
            elif 0.9 <= sim <= 1.0:
                analysis["similarity_distribution"]["0.9-1.0"] += 1

        # ランク分布
        for hn in hard_negatives:
            rank = str(hn["rank"])
            if rank not in analysis["rank_distribution"]:
                analysis["rank_distribution"][rank] = 0
            analysis["rank_distribution"][rank] += 1

        # 最も混同されやすいペア
        confusion_counts = {}
        for hn in hard_negatives:
            if "correct_item_name" in hn:
                pair = (hn["correct_item_name"], hn["negative_item_name"])
                if pair not in confusion_counts:
                    confusion_counts[pair] = 0
                confusion_counts[pair] += 1

        # Top 10 confused pairs
        sorted_pairs = sorted(
            confusion_counts.items(), key=lambda x: x[1], reverse=True
        )
        analysis["top_confused_pairs"] = [
            {"correct": pair[0], "confused_with": pair[1], "count": count}
            for (pair, count) in sorted_pairs[:10]
        ]

        return analysis


def main():
    parser = argparse.ArgumentParser(description="Mine hard negatives from search logs")
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to look back"
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=0.5,
        help="Minimum similarity for hard negatives",
    )
    parser.add_argument(
        "--max-rank", type=int, default=10, help="Maximum rank to consider"
    )
    parser.add_argument(
        "--min-rank",
        type=int,
        default=2,
        help="Minimum rank to consider (exclude top-1)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/hard_negatives.json",
        help="Output file path",
    )
    parser.add_argument("--triplets", type=str, help="Output path for triplets")
    parser.add_argument("--analyze", action="store_true", help="Analyze hard negatives")

    args = parser.parse_args()

    # Database setup
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        miner = HardNegativeMiner(session)

        print(f"\n🔍 Mining hard negatives from the last {args.days} days...")
        print(f"   Min similarity: {args.min_similarity}")
        print(f"   Rank range: {args.min_rank}-{args.max_rank}")

        # Collect hard negatives
        hard_negatives = miner.collect_hard_negatives(
            days_back=args.days,
            min_similarity=args.min_similarity,
            max_rank=args.max_rank,
            min_rank=args.min_rank,
        )

        print(f"\n📊 Found {len(hard_negatives)} hard negatives")

        # Analyze if requested
        if args.analyze:
            analysis = miner.analyze_hard_negatives(hard_negatives)

            print("\n📈 Analysis:")
            print(f"   Total hard negatives: {analysis['total_count']}")

            print("\n   Category confusion matrix:")
            for pair, count in sorted(
                analysis["category_distribution"].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10]:
                print(f"     {pair}: {count}")

            print("\n   Similarity distribution:")
            for range_str, count in analysis["similarity_distribution"].items():
                if count > 0:
                    print(f"     {range_str}: {count}")

            print("\n   Top confused pairs:")
            for pair in analysis["top_confused_pairs"][:5]:
                print(
                    f"     '{pair['correct']}' ↔ '{pair['confused_with']}': {pair['count']} times"
                )

        # Save hard negatives
        if hard_negatives:
            new_count = miner.save_hard_negatives(hard_negatives, args.output)
            print(f"\n💾 Saved {new_count} new hard negatives to: {args.output}")

            # Create triplets if requested
            if args.triplets:
                triplets = miner.create_triplets(hard_negatives)

                triplets_path = Path(args.triplets)
                triplets_path.parent.mkdir(parents=True, exist_ok=True)

                with open(triplets_path, "w") as f:
                    json.dump(triplets, f, indent=2, ensure_ascii=False)

                print(f"💾 Saved {len(triplets)} triplets to: {args.triplets}")

        # Display some examples
        if hard_negatives:
            print("\n📋 Example hard negatives:")
            for i, hn in enumerate(hard_negatives[:3], 1):
                print(f"\n  {i}. Detection: {hn['detected_description'][:50]}...")
                print(
                    f"     Confused: '{hn['negative_item_name']}' (rank {hn['rank']}, sim={hn['similarity']:.3f})"
                )
                if "correct_item_name" in hn:
                    print(f"     Correct: '{hn['correct_item_name']}'")

    finally:
        session.close()


if __name__ == "__main__":
    main()
