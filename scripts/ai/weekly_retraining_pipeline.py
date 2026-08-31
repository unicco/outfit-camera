#!/usr/bin/env python3
"""Weekly retraining pipeline for reranker and embedding models."""

import json
import subprocess
from datetime import datetime
from pathlib import Path
import argparse
import logging
from typing import Dict, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/retraining_pipeline.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class RetrainingPipeline:
    """週次再学習パイプライン."""

    def __init__(self, config_path: str):
        with open(config_path, "r") as f:
            self.config = json.load(f)

        self.data_dir = Path(self.config.get("data_dir", "data"))
        self.model_dir = Path(self.config.get("model_dir", "models"))
        self.checkpoint_dir = Path(self.config.get("checkpoint_dir", "checkpoints"))

        # Create directories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def run_evaluation(self, days: int = 7) -> Dict[str, Any]:
        """現在のモデルの評価を実行."""
        logger.info("🔍 Running model evaluation...")

        output_path = self.data_dir / f"evaluation_{self.timestamp}.json"

        cmd = [
            "python",
            "api/scripts/evaluation/evaluate_reranker.py",
            "--days",
            str(days),
            "--output",
            str(output_path),
            "--analyze-failures",
        ]

        # Add baseline if exists
        baseline_path = self.data_dir / "baseline_metrics.json"
        if baseline_path.exists():
            cmd.extend(["--baseline", str(baseline_path)])

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Evaluation failed: {result.stderr}")
            return {}

        # Load evaluation results
        with open(output_path, "r") as f:
            return json.load(f)

    def collect_hard_negatives(self, days: int = 7) -> str:
        """ハードネガティブを収集."""
        logger.info("🔍 Collecting hard negatives...")

        output_path = self.data_dir / f"hard_negatives_{self.timestamp}.json"
        triplets_path = self.data_dir / f"triplets_{self.timestamp}.json"

        cmd = [
            "python",
            "scripts/ai/hard_negative_miner.py",
            "--days",
            str(days),
            "--min-similarity",
            str(self.config.get("min_similarity", 0.5)),
            "--max-rank",
            str(self.config.get("max_rank", 10)),
            "--output",
            str(output_path),
            "--triplets",
            str(triplets_path),
            "--analyze",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Hard negative mining failed: {result.stderr}")
            return ""

        logger.info(f"✅ Collected hard negatives: {output_path}")
        return str(triplets_path)

    def train_reranker(self, evaluation_results: Dict[str, Any]) -> bool:
        """再ランカーの学習."""
        logger.info("🏃 Training reranker model...")

        # Prepare training data from search logs
        # This is a simplified version - in practice, you'd extract features
        # from the search logs and prepare them for training

        training_data_path = self.data_dir / f"reranker_training_{self.timestamp}.json"
        logger.debug("Training data placeholder path: %s", training_data_path)

        # TODO: Implement actual training data preparation
        # For now, we'll skip this step
        logger.warning("Reranker training not yet implemented")

        return True

    def train_embedding_adapter(self, triplets_path: str) -> bool:
        """埋め込みアダプターの学習."""
        if not triplets_path or not Path(triplets_path).exists():
            logger.warning("No triplets found, skipping embedding adapter training")
            return False

        logger.info("🏃 Training embedding adapter...")

        checkpoint_subdir = self.checkpoint_dir / f"embedding_{self.timestamp}"

        cmd = [
            "python",
            "scripts/ai/train_with_hardnegs.py",
            "--triplets",
            triplets_path,
            "--loss",
            self.config.get("loss_type", "triplet"),
            "--epochs",
            str(self.config.get("epochs", 50)),
            "--batch-size",
            str(self.config.get("batch_size", 32)),
            "--learning-rate",
            str(self.config.get("learning_rate", 1e-4)),
            "--checkpoint-dir",
            str(checkpoint_subdir),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Embedding training failed: {result.stderr}")
            return False

        # Copy best model to model directory
        best_model = checkpoint_subdir / "best_model.pth"
        if best_model.exists():
            target_path = self.model_dir / f"embedding_adapter_{self.timestamp}.pth"
            import shutil

            shutil.copy(best_model, target_path)
            logger.info(f"✅ Saved embedding adapter: {target_path}")

            # Update symlink to latest model
            latest_link = self.model_dir / "embedding_adapter_latest.pth"
            if latest_link.exists():
                latest_link.unlink()
            latest_link.symlink_to(target_path.name)

        return True

    def update_production_models(self, evaluation_results: Dict[str, Any]) -> bool:
        """本番モデルを更新."""
        logger.info("🚀 Updating production models...")

        # Check if new models improve performance
        if not evaluation_results:
            logger.warning("No evaluation results, skipping model update")
            return False

        metrics = evaluation_results.get("metrics", {})
        if metrics:
            logger.debug(
                "Evaluation metrics snapshot: top1=%.2f, top5=%.2f",
                metrics.get("top1_accuracy", 0.0),
                metrics.get("top5_accuracy", 0.0),
            )
        comparison = evaluation_results.get("comparison", {})

        # Decision logic: update if average improvement > threshold
        if comparison:
            avg_improvement = comparison.get("summary", {}).get(
                "average_improvement", 0
            )
            threshold = self.config.get("improvement_threshold", 2.0)  # 2% improvement

            if avg_improvement < threshold:
                logger.info(
                    f"Average improvement ({avg_improvement:.1f}%) below threshold ({threshold}%), skipping update"
                )
                return False

        # TODO: Implement actual model deployment
        logger.info("✅ Models would be updated in production")

        return True

    def generate_report(
        self,
        evaluation_before: Dict[str, Any],
        evaluation_after: Optional[Dict[str, Any]] = None,
    ) -> str:
        """再学習レポートを生成."""
        logger.info("📊 Generating retraining report...")

        report_path = self.data_dir / f"retraining_report_{self.timestamp}.md"

        with open(report_path, "w") as f:
            f.write("# 再学習パイプライン実行レポート\n\n")
            f.write(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Before metrics
            if evaluation_before:
                metrics = evaluation_before.get("metrics", {})
                f.write("## 再学習前のメトリクス\n\n")
                f.write(f"- Top-1 精度: {metrics.get('top1_accuracy', 0):.2%}\n")
                f.write(f"- Top-5 精度: {metrics.get('top5_accuracy', 0):.2%}\n")
                f.write(f"- MRR: {metrics.get('mrr', 0):.3f}\n")
                f.write(f"- mAP: {metrics.get('map', 0):.3f}\n\n")

            # After metrics (if available)
            if evaluation_after:
                metrics = evaluation_after.get("metrics", {})
                f.write("## 再学習後のメトリクス\n\n")
                f.write(f"- Top-1 精度: {metrics.get('top1_accuracy', 0):.2%}\n")
                f.write(f"- Top-5 精度: {metrics.get('top5_accuracy', 0):.2%}\n")
                f.write(f"- MRR: {metrics.get('mrr', 0):.3f}\n")
                f.write(f"- mAP: {metrics.get('map', 0):.3f}\n\n")

                # Comparison
                comparison = evaluation_after.get("comparison", {})
                if comparison:
                    f.write("## 改善率\n\n")
                    improvements = comparison.get("improvements", {})
                    for metric, data in improvements.items():
                        symbol = "✅" if data["improved"] else "❌"
                        f.write(
                            f"- {symbol} {metric}: {data['improvement_percent']:+.1f}%\n"
                        )

            # Hard negatives analysis
            hard_neg_path = self.data_dir / f"hard_negatives_{self.timestamp}.json"
            if hard_neg_path.exists():
                with open(hard_neg_path, "r") as hn_file:
                    hard_negatives = json.load(hn_file)
                f.write("\n## ハードネガティブ分析\n\n")
                f.write(f"- 収集数: {len(hard_negatives)}\n")

        logger.info(f"✅ Report saved: {report_path}")
        return str(report_path)

    def run_pipeline(self):
        """完全な再学習パイプラインを実行."""
        logger.info("🚀 Starting weekly retraining pipeline...")

        try:
            # Step 1: Evaluate current model
            evaluation_before = self.run_evaluation()

            # Step 2: Collect hard negatives
            triplets_path = self.collect_hard_negatives()

            # Step 3: Train reranker
            reranker_success = self.train_reranker(evaluation_before)

            # Step 4: Train embedding adapter
            embedding_success = False
            if triplets_path:
                embedding_success = self.train_embedding_adapter(triplets_path)

            # Step 5: Evaluate new models
            evaluation_after = None
            if reranker_success or embedding_success:
                evaluation_after = self.run_evaluation()

            # Step 6: Update production models if improved
            if evaluation_after:
                self.update_production_models(evaluation_after)

            # Step 7: Generate report
            report_path = self.generate_report(evaluation_before, evaluation_after)

            # Send notification (e.g., email, Slack)
            self.send_notification(report_path)

            logger.info("✅ Pipeline completed successfully")

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            raise

    def send_notification(self, report_path: str):
        """完了通知を送信."""
        # TODO: Implement actual notification (email, Slack, etc.)
        logger.info(f"📧 Notification would be sent with report: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Weekly retraining pipeline")
    parser.add_argument(
        "--config",
        type=str,
        default="config/retraining_config.json",
        help="Configuration file path",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Run evaluation only, don't train"
    )

    args = parser.parse_args()

    # Default configuration
    default_config = {
        "data_dir": "data/retraining",
        "model_dir": "models",
        "checkpoint_dir": "checkpoints",
        "min_similarity": 0.5,
        "max_rank": 10,
        "loss_type": "triplet",
        "epochs": 50,
        "batch_size": 32,
        "learning_rate": 1e-4,
        "improvement_threshold": 2.0,
    }

    # Load or create config
    config_path = Path(args.config)
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=2)
        logger.info(f"Created default config: {config_path}")

    # Run pipeline
    pipeline = RetrainingPipeline(str(config_path))

    if args.dry_run:
        logger.info("🧪 Running in dry-run mode (evaluation only)")
        evaluation = pipeline.run_evaluation()
        report = pipeline.generate_report(evaluation)
        logger.info(f"Dry run completed. Report: {report}")
    else:
        pipeline.run_pipeline()


if __name__ == "__main__":
    main()
