#!/usr/bin/env python3
"""Offline evaluation script for reranking model."""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from app import wardrobe_models  # noqa: F401  # Ensure clothing models are registered
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.search_log_models import SearchLog


def calculate_metrics(search_logs: List[SearchLog]) -> Dict[str, Any]:
    """検索ログから評価メトリクスを計算.

    Returns:
        - top1_accuracy: Top-1精度
        - top5_accuracy: Top-5精度
        - map: Mean Average Precision
        - mrr: Mean Reciprocal Rank
        - category_metrics: カテゴリ別メトリクス

    """
    total_queries = 0
    correct_top1 = 0
    correct_top5 = 0
    reciprocal_ranks = []
    average_precisions = []
    category_stats = {}

    for log in search_logs:
        if not log.search_results:
            continue

        total_queries += 1
        category = log.detected_category

        if category not in category_stats:
            category_stats[category] = {
                "total": 0,
                "correct_top1": 0,
                "correct_top5": 0,
                "reciprocal_ranks": [],
                "average_precisions": [],
            }

        category_stats[category]["total"] += 1

        # Find correct item rank
        correct_rank = None
        for result in log.search_results:
            if result.is_correct:
                correct_rank = result.rank
                break

        if correct_rank:
            # Top-1 accuracy
            if correct_rank == 1:
                correct_top1 += 1
                category_stats[category]["correct_top1"] += 1

            # Top-5 accuracy
            if correct_rank <= 5:
                correct_top5 += 1
                category_stats[category]["correct_top5"] += 1

            # Mean Reciprocal Rank
            rr = 1.0 / correct_rank
            reciprocal_ranks.append(rr)
            category_stats[category]["reciprocal_ranks"].append(rr)

            # Average Precision (simplified - assumes binary relevance)
            # Count correct items up to and including the correct rank
            correct_up_to_rank = sum(
                1 for r in log.search_results if r.rank <= correct_rank and r.is_correct
            )
            ap = correct_up_to_rank / correct_rank
            average_precisions.append(ap)
            category_stats[category]["average_precisions"].append(ap)

    # Calculate overall metrics
    metrics = {
        "total_queries": total_queries,
        "queries_with_feedback": len(
            [
                log_entry
                for log_entry in search_logs
                if any(r.is_correct is not None for r in log_entry.search_results)
            ]
        ),
        "top1_accuracy": correct_top1 / total_queries if total_queries > 0 else 0.0,
        "top5_accuracy": correct_top5 / total_queries if total_queries > 0 else 0.0,
        "mrr": np.mean(reciprocal_ranks) if reciprocal_ranks else 0.0,
        "map": np.mean(average_precisions) if average_precisions else 0.0,
        "category_metrics": {},
    }

    # Calculate per-category metrics
    for category, stats in category_stats.items():
        if stats["total"] > 0:
            metrics["category_metrics"][category] = {
                "total": stats["total"],
                "top1_accuracy": stats["correct_top1"] / stats["total"],
                "top5_accuracy": stats["correct_top5"] / stats["total"],
                "mrr": (
                    np.mean(stats["reciprocal_ranks"])
                    if stats["reciprocal_ranks"]
                    else 0.0
                ),
                "map": (
                    np.mean(stats["average_precisions"])
                    if stats["average_precisions"]
                    else 0.0
                ),
            }

    return metrics


def compare_with_baseline(
    current_metrics: Dict[str, Any], baseline_metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """現在のメトリクスをベースラインと比較.

    Returns:
        改善率などの比較結果

    """
    comparison = {"improvements": {}, "summary": {}}

    # Compare main metrics
    for metric in ["top1_accuracy", "top5_accuracy", "mrr", "map"]:
        if metric in baseline_metrics and metric in current_metrics:
            baseline_val = baseline_metrics[metric]
            current_val = current_metrics[metric]

            if baseline_val > 0:
                improvement = ((current_val - baseline_val) / baseline_val) * 100
            else:
                improvement = 100.0 if current_val > 0 else 0.0

            comparison["improvements"][metric] = {
                "baseline": baseline_val,
                "current": current_val,
                "improvement_percent": improvement,
                "improved": current_val > baseline_val,
            }

    # Overall summary
    avg_improvement = np.mean(
        [comp["improvement_percent"] for comp in comparison["improvements"].values()]
    )

    comparison["summary"] = {
        "average_improvement": avg_improvement,
        "metrics_improved": sum(
            1 for comp in comparison["improvements"].values() if comp["improved"]
        ),
        "metrics_total": len(comparison["improvements"]),
    }

    return comparison


def analyze_failure_cases(
    search_logs: List[SearchLog], top_n: int = 10
) -> List[Dict[str, Any]]:
    """失敗ケース（誤認識）を分析.

    Returns:
        失敗ケースの詳細リスト

    """
    failures = []

    for log in search_logs:
        if not log.search_results:
            continue

        # Check if top-1 is incorrect
        top1_result = next((r for r in log.search_results if r.rank == 1), None)
        if top1_result and not top1_result.is_correct:
            # Find the correct item's rank
            correct_result = next((r for r in log.search_results if r.is_correct), None)

            failure_info = {
                "search_log_id": log.id,
                "detected_category": log.detected_category,
                "detected_description": log.detected_description,
                "timestamp": log.timestamp.isoformat(),
                "top1_item_id": top1_result.wardrobe_item_id,
                "top1_similarity": top1_result.embedding_similarity,
                "correct_item_rank": correct_result.rank if correct_result else None,
                "correct_item_similarity": (
                    correct_result.embedding_similarity if correct_result else None
                ),
                "similarity_gap": (
                    top1_result.embedding_similarity
                    - correct_result.embedding_similarity
                    if correct_result
                    else None
                ),
            }

            failures.append(failure_info)

    # Sort by similarity gap (largest gaps first - these are the hardest cases)
    failures.sort(key=lambda x: x.get("similarity_gap", 0), reverse=True)

    return failures[:top_n]


def main():
    parser = argparse.ArgumentParser(description="Evaluate reranking model performance")
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to evaluate"
    )
    parser.add_argument(
        "--baseline", type=str, help="Path to baseline metrics JSON file"
    )
    parser.add_argument("--output", type=str, help="Path to save evaluation results")
    parser.add_argument(
        "--analyze-failures", action="store_true", help="Analyze failure cases"
    )

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
        # Get search logs
        cutoff_date = datetime.now() - timedelta(days=args.days)

        search_logs = (
            session.query(SearchLog).filter(SearchLog.timestamp >= cutoff_date).all()
        )

        print(
            f"\n📊 Evaluating {len(search_logs)} search logs from the last {args.days} days"
        )

        # Calculate metrics
        metrics = calculate_metrics(search_logs)

        # Display results
        print("\n🎯 Overall Metrics:")
        print(f"  Total queries: {metrics['total_queries']}")
        print(f"  Queries with feedback: {metrics['queries_with_feedback']}")
        print(f"  Top-1 accuracy: {metrics['top1_accuracy']:.2%}")
        print(f"  Top-5 accuracy: {metrics['top5_accuracy']:.2%}")
        print(f"  Mean Reciprocal Rank (MRR): {metrics['mrr']:.3f}")
        print(f"  Mean Average Precision (mAP): {metrics['map']:.3f}")

        # Category breakdown
        if metrics["category_metrics"]:
            print("\n📈 Category Breakdown:")
            for category, cat_metrics in metrics["category_metrics"].items():
                print(f"\n  {category}:")
                print(f"    Queries: {cat_metrics['total']}")
                print(f"    Top-1: {cat_metrics['top1_accuracy']:.2%}")
                print(f"    Top-5: {cat_metrics['top5_accuracy']:.2%}")
                print(f"    MRR: {cat_metrics['mrr']:.3f}")

        # Compare with baseline if provided
        if args.baseline and Path(args.baseline).exists():
            with open(args.baseline, "r") as f:
                baseline_metrics = json.load(f)

            comparison = compare_with_baseline(metrics, baseline_metrics)

            print("\n📊 Comparison with Baseline:")
            for metric, comp in comparison["improvements"].items():
                symbol = "✅" if comp["improved"] else "❌"
                print(
                    f"  {symbol} {metric}: {comp['baseline']:.3f} → {comp['current']:.3f} "
                    f"({comp['improvement_percent']:+.1f}%)"
                )

            print(
                f"\n  Average improvement: {comparison['summary']['average_improvement']:+.1f}%"
            )
            print(
                f"  Metrics improved: {comparison['summary']['metrics_improved']}/{comparison['summary']['metrics_total']}"
            )

        # Analyze failures if requested
        if args.analyze_failures:
            failures = analyze_failure_cases(search_logs, top_n=10)

            if failures:
                print("\n❌ Top Failure Cases (Hard Negatives):")
                for i, failure in enumerate(failures, 1):
                    print(f"\n  {i}. Category: {failure['detected_category']}")
                    print(
                        f"     Description: {failure['detected_description'][:50]}..."
                    )
                    print(f"     Top-1 similarity: {failure['top1_similarity']:.3f}")
                    if failure["correct_item_rank"]:
                        print(f"     Correct item rank: {failure['correct_item_rank']}")
                        print(
                            f"     Correct similarity: {failure['correct_item_similarity']:.3f}"
                        )
                        print(f"     Similarity gap: {failure['similarity_gap']:.3f}")

        # Save results if requested
        if args.output:
            results = {
                "evaluation_date": datetime.now().isoformat(),
                "days_evaluated": args.days,
                "metrics": metrics,
                "comparison": comparison if args.baseline else None,
                "failures": (
                    analyze_failure_cases(search_logs, top_n=20)
                    if args.analyze_failures
                    else None
                ),
            }

            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            print(f"\n💾 Results saved to: {output_path}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
