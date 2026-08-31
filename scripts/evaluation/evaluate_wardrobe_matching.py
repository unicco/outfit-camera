"""ワードローブマッチング精度の評価スクリプト（Hit@K）.

テスト画像に対してマッチングパイプライン（embedding 生成 + 類似度検索）を実行し、
正解のワードローブアイテムが Top-K に含まれるかを評価する。

DB 接続が必要。DB が利用できない場合はスキップする。

使い方:
    python scripts/evaluation/evaluate_wardrobe_matching.py \
        --test-dir scripts/evaluation/test_images/ \
        --ground-truth scripts/evaluation/matching_ground_truth.json \
        --k 5

    # Hit@1, Hit@3, Hit@5 を一括表示
    python scripts/evaluation/evaluate_wardrobe_matching.py \
        --test-dir scripts/evaluation/test_images/ \
        --ground-truth scripts/evaluation/matching_ground_truth.json \
        --k 1 3 5
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# プロジェクトルートを sys.path に追加
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root / "api"))
sys.path.insert(0, str(_project_root / "src"))

logger = logging.getLogger(__name__)


def _check_dependencies() -> Optional[str]:
    """必要な依存関係をチェック.

    Returns:
        エラーメッセージ（問題なければ None）

    """
    try:
        import numpy  # noqa: F401
    except ImportError:
        return "numpy がインストールされていません"

    # Jina API キーの確認
    if not os.getenv("JINA_API_KEY"):
        return "JINA_API_KEY 環境変数が設定されていません"

    # DB 接続の確認
    try:
        from app.database import get_db  # noqa: F401
    except ImportError:
        return "DB モジュールを読み込めません（api/app/database.py）"

    return None


def _get_db_session():
    """DB セッションを取得する."""
    from app.database import get_db

    return next(get_db())


def _generate_embedding(image_path: str) -> Optional[Any]:
    """テスト画像の embedding を生成する."""
    try:
        from coordinate_recorder.jina_api_service import JinaAPIService

        api_key = os.getenv("JINA_API_KEY", "")
        service = JinaAPIService(api_key=api_key)
        result = service.generate_embedding(
            image=image_path,
            use_cache=True,
            task="retrieval.query",
        )
        if result.success:
            return result.embedding
        logger.warning(f"Embedding 生成に失敗: {result.error_message}")
        return None
    except Exception as e:
        logger.error(f"Embedding 生成中にエラー: {e}")
        return None


def _search_similar_items(
    embedding: Any,
    category: Optional[str] = None,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """embedding ベースで類似ワードローブアイテムを検索する."""
    import numpy as np

    from app.wardrobe_models import ClothingCategory, ClothingItem, ClothingStatus

    db = _get_db_session()

    try:
        # カテゴリフィルタ
        query = db.query(ClothingItem).filter(
            ClothingItem.status == ClothingStatus.ACTIVE,
            ClothingItem.embedding_vector.isnot(None),
        )

        if category:
            category_map = {
                "tops": ClothingCategory.TOPS,
                "bottoms": ClothingCategory.BOTTOMS,
                "outerwear": ClothingCategory.OUTERWEAR,
                "dresses": ClothingCategory.DRESSES,
                "shoes": ClothingCategory.SHOES,
                "accessories": ClothingCategory.ACCESSORIES,
                "bag": ClothingCategory.BAG,
                "other": ClothingCategory.OTHER,
            }
            cat_enum = category_map.get(category.lower())
            if cat_enum:
                query = query.filter(ClothingItem.category == cat_enum)

        candidates = query.all()

        if not candidates:
            logger.warning("embedding 付きのワードローブアイテムが見つかりません")
            return []

        # コサイン類似度で順位付け
        query_vec = np.array(embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        scored = []
        for item in candidates:
            item_vec = np.array(item.embedding_vector, dtype=np.float32)
            item_norm = np.linalg.norm(item_vec)
            if item_norm == 0:
                continue
            similarity = float(np.dot(query_vec, item_vec) / (query_norm * item_norm))
            scored.append(
                {
                    "item_id": item.id,
                    "name": item.name,
                    "category": item.category.value if item.category else None,
                    "similarity": round(similarity, 4),
                }
            )

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    finally:
        db.close()


def load_ground_truth(path: Path) -> Dict[str, Dict[str, Any]]:
    """正解データを読み込む（_ 始まりのキーは除外）."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def evaluate_single_image(
    image_path: Path,
    ground_truth: Dict[str, Any],
    max_k: int = 10,
) -> Dict[str, Any]:
    """1枚の画像に対してマッチング評価を実行する.

    Returns:
        評価結果の辞書

    """
    result: Dict[str, Any] = {
        "image": image_path.name,
        "ground_truth": ground_truth,
        "status": "error",
    }

    correct_item_id = ground_truth.get("correct_item_id")
    if correct_item_id is None:
        result["error"] = "correct_item_id が正解データにありません"
        return result

    # Embedding 生成
    logger.info(f"Embedding 生成中: {image_path.name}")
    embedding = _generate_embedding(str(image_path))
    if embedding is None:
        result["error"] = "Embedding の生成に失敗しました"
        return result

    # 類似アイテム検索
    category = ground_truth.get("category")
    matches = _search_similar_items(embedding, category=category, top_k=max_k)

    result["matches"] = matches
    result["num_matches"] = len(matches)

    # Hit@K の判定
    matched_ids = [m["item_id"] for m in matches]
    hit_at: Dict[str, bool] = {}
    for k in [1, 3, 5, 10]:
        if k <= max_k:
            hit_at[f"hit@{k}"] = correct_item_id in matched_ids[:k]

    result["hit_at"] = hit_at

    # 正解アイテムの順位
    if correct_item_id in matched_ids:
        result["correct_rank"] = matched_ids.index(correct_item_id) + 1
    else:
        result["correct_rank"] = None

    result["status"] = "ok"
    return result


def run_evaluation(
    test_dir: Path,
    ground_truth_path: Path,
    k_values: List[int],
) -> Dict[str, Any]:
    """全テスト画像に対して評価を実行する.

    Returns:
        評価レポート全体

    """
    ground_truth = load_ground_truth(ground_truth_path)

    if not ground_truth:
        logger.warning("正解データが空です")
        return {"error": "正解データが空です", "results": []}

    max_k = max(k_values) if k_values else 5
    results: List[Dict[str, Any]] = []
    hit_counts: Dict[str, int] = {f"hit@{k}": 0 for k in k_values}
    evaluated = 0
    ranks: List[int] = []

    for image_name, gt_data in ground_truth.items():
        image_path = test_dir / image_name
        if not image_path.exists():
            logger.warning(f"テスト画像が見つかりません: {image_path}")
            results.append(
                {
                    "image": image_name,
                    "status": "skipped",
                    "reason": "ファイルが見つかりません",
                }
            )
            continue

        logger.info(f"評価中: {image_name}")
        result = evaluate_single_image(image_path, gt_data, max_k=max_k)
        results.append(result)

        if result["status"] == "ok":
            evaluated += 1
            for k in k_values:
                key = f"hit@{k}"
                if result.get("hit_at", {}).get(key, False):
                    hit_counts[key] += 1
            if result.get("correct_rank") is not None:
                ranks.append(result["correct_rank"])

    # サマリー
    summary: Dict[str, Any] = {
        "total_images": len(results),
        "evaluated": evaluated,
        "skipped": len(results) - evaluated,
        "k_values": k_values,
    }

    if evaluated > 0:
        hit_rates = {}
        for k in k_values:
            key = f"hit@{k}"
            hit_rates[key] = {
                "count": hit_counts[key],
                "rate": round(hit_counts[key] / evaluated * 100, 1),
            }
        summary["hit_rates"] = hit_rates

        if ranks:
            import numpy as np

            arr = np.array(ranks)
            summary["rank_stats"] = {
                "mean": round(float(np.mean(arr)), 2),
                "median": round(float(np.median(arr)), 2),
                "found_in_top_k": len(ranks),
                "not_found": evaluated - len(ranks),
            }
    else:
        summary["hit_rates"] = {}

    return {"summary": summary, "results": results}


def print_report(report: Dict[str, Any]) -> None:
    """評価レポートを見やすく出力する."""
    summary = report.get("summary", {})
    results = report.get("results", [])

    logger.info("=" * 60)
    logger.info("ワードローブマッチング精度 評価レポート（Hit@K）")
    logger.info("=" * 60)

    logger.info(
        f"評価画像数: {summary.get('evaluated', 0)} / {summary.get('total_images', 0)}"
    )

    hit_rates = summary.get("hit_rates", {})
    if hit_rates:
        logger.info("")
        logger.info("--- Hit@K ---")
        for key, data in hit_rates.items():
            logger.info(
                f"  {key}: {data['rate']}% ({data['count']}/{summary['evaluated']})"
            )

    rank_stats = summary.get("rank_stats")
    if rank_stats:
        logger.info("")
        logger.info("--- 正解アイテム順位統計 ---")
        logger.info(f"  平均順位: {rank_stats.get('mean', 'N/A')}")
        logger.info(f"  中央値:   {rank_stats.get('median', 'N/A')}")
        logger.info(f"  Top-K 内: {rank_stats.get('found_in_top_k', 0)}")
        logger.info(f"  未発見:   {rank_stats.get('not_found', 0)}")

    # 個別結果
    logger.info("")
    logger.info("--- 個別結果 ---")
    for r in results:
        if r.get("status") == "skipped":
            logger.info(f"  [{r['image']}] SKIP - {r.get('reason', '')}")
            continue
        if r.get("status") == "error":
            logger.info(f"  [{r['image']}] ERROR - {r.get('error', '')}")
            continue

        rank = r.get("correct_rank")
        rank_str = f"rank={rank}" if rank else "NOT FOUND"
        hits = r.get("hit_at", {})
        hit_str = " ".join(f"{k}={'Y' if v else 'N'}" for k, v in sorted(hits.items()))
        logger.info(f"  [{r['image']}] {rank_str} | {hit_str}")

    logger.info("=" * 60)


def main() -> None:
    """メインエントリポイント."""
    parser = argparse.ArgumentParser(
        description="ワードローブマッチング精度の評価スクリプト（Hit@K）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path(__file__).parent / "test_images",
        help="テスト画像のディレクトリ（デフォルト: scripts/evaluation/test_images/）",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path(__file__).parent / "matching_ground_truth.json",
        help="正解データの JSON ファイル",
    )
    parser.add_argument(
        "--k",
        type=int,
        nargs="+",
        default=[1, 3, 5],
        help="評価する K 値（デフォルト: 1 3 5）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="結果を JSON ファイルに出力",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="詳細ログを出力",
    )

    args = parser.parse_args()

    # ログ設定
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 依存関係チェック
    dep_error = _check_dependencies()
    if dep_error:
        logger.warning(f"依存関係の問題によりスキップ: {dep_error}")
        logger.info("このスクリプトの実行には DB 接続と JINA_API_KEY が必要です。")
        sys.exit(0)

    # 入力チェック
    if not args.test_dir.is_dir():
        logger.error(f"テスト画像ディレクトリが見つかりません: {args.test_dir}")
        sys.exit(1)

    if not args.ground_truth.is_file():
        logger.error(f"正解データファイルが見つかりません: {args.ground_truth}")
        sys.exit(1)

    # 評価実行
    report = run_evaluation(
        test_dir=args.test_dir,
        ground_truth_path=args.ground_truth,
        k_values=sorted(args.k),
    )

    # レポート出力
    print_report(report)

    # JSON 出力（オプション）
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"結果を保存しました: {args.output}")


if __name__ == "__main__":
    main()
