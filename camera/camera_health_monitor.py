"""カメラサービス内蔵ヘルスモニター
メモリリーク、GPU メモリ、フレーム処理の健全性を監視.
"""

import gc
import psutil
import threading
import time
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class CameraHealthMonitor:
    """カメラサービスの内部健全性を監視."""

    def __init__(self, camera_service_instance):
        self.camera_service = camera_service_instance
        self.monitoring = False
        self.monitor_thread = None

        # 監視設定 - 環境別に調整
        self.memory_threshold_mb = self._get_memory_threshold()  # 環境に応じて調整
        self.frame_timeout_seconds = 10  # 10秒間フレーム更新がないとアラート
        self.check_interval = 30  # 30秒間隔で監視

        # 統計情報
        self.stats = {
            "last_frame_time": time.time(),
            "memory_usage_mb": 0,
            "frame_count": 0,
            "restart_count": 0,
            "last_restart_time": None,
        }

    def _get_memory_threshold(self):
        """環境に応じたメモリ閾値を取得."""
        try:
            import platform

            # Raspberry Pi 環境を検出
            machine = platform.machine().lower()
            is_raspberry_pi = any(arch in machine for arch in ["arm", "aarch64"])

            if is_raspberry_pi:
                # Raspberry Pi: より低い閾値（メモリが限られているため）
                threshold = 300
                logger.info(
                    f"🍓 Raspberry Pi environment detected, using memory threshold: {threshold}MB"
                )
            else:
                # 開発環境・PC環境: 標準的な閾値
                threshold = 500
                logger.info(
                    f"💻 Development environment detected, using memory threshold: {threshold}MB"
                )

            return threshold

        except Exception as e:
            logger.warning(
                f"Failed to detect environment, using default threshold: {e}"
            )
            return 500  # デフォルト値

    def start_monitoring(self):
        """監視を開始."""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("🔍 Camera health monitoring started")

    def stop_monitoring(self):
        """監視を停止."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("🛑 Camera health monitoring stopped")

    def update_frame_timestamp(self):
        """新しいフレームが処理された時に呼び出す."""
        self.stats["last_frame_time"] = time.time()
        self.stats["frame_count"] += 1

    def _monitor_loop(self):
        """メイン監視ループ."""
        while self.monitoring:
            try:
                self._check_memory_usage()
                self._check_frame_freshness()
                self._check_gpu_memory()
                self._cleanup_resources()

            except Exception as e:
                logger.error(f"Health monitor error: {e}")

            time.sleep(self.check_interval)

    def _check_memory_usage(self):
        """メモリ使用量をチェック."""
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.stats["memory_usage_mb"] = memory_mb

            if memory_mb > self.memory_threshold_mb:
                logger.warning(f"⚠️ High memory usage: {memory_mb:.1f}MB")

                # メモリ使用量が異常に高い場合は強制ガベージコレクション
                if memory_mb > self.memory_threshold_mb * 1.5:
                    logger.info("🧹 Force garbage collection")
                    gc.collect()

                # それでも改善しない場合は再起動をトリガー
                if memory_mb > self.memory_threshold_mb * 2:
                    logger.error(f"🚨 Critical memory usage: {memory_mb:.1f}MB")
                    self._trigger_self_restart("Critical memory usage")

        except Exception as e:
            logger.error(f"Memory check failed: {e}")

    def _check_frame_freshness(self):
        """フレームの新鮮さをチェック."""
        time_since_last_frame = time.time() - self.stats["last_frame_time"]

        if time_since_last_frame > self.frame_timeout_seconds:
            logger.warning(f"⚠️ No new frames for {time_since_last_frame:.1f}s")

            # フレームが長時間更新されない場合は再起動
            if time_since_last_frame > self.frame_timeout_seconds * 2:
                logger.error(f"🚨 Frame timeout: {time_since_last_frame:.1f}s")
                self._trigger_self_restart("Frame processing timeout")

    def _check_gpu_memory(self):
        """GPU メモリをチェック（Raspberry Pi の場合）."""
        try:
            import shutil
            import subprocess

            # vcgencmd コマンドの存在確認
            if not shutil.which("vcgencmd"):
                logger.debug("vcgencmd not available, skipping GPU memory check")
                return

            result = subprocess.run(
                ["vcgencmd", "get_mem", "gpu"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                gpu_mem = result.stdout.strip()
                logger.debug(f"GPU memory: {gpu_mem}")

        except Exception as e:
            logger.debug(f"GPU memory check failed: {e}")

    def _cleanup_resources(self):
        """定期的なリソースクリーンアップ."""
        try:
            # Python のガベージコレクション
            collected = gc.collect()
            if collected > 0:
                logger.debug(f"🧹 Garbage collected {collected} objects")

            # Picamera2 の内部状態をチェック
            if hasattr(self.camera_service, "picamera2"):
                picamera2 = self.camera_service.picamera2
                if picamera2 and hasattr(picamera2, "started"):
                    if not picamera2.started:
                        logger.warning("⚠️ Picamera2 not started, attempting restart")
                        self._trigger_camera_restart()

        except Exception as e:
            logger.error(f"Resource cleanup failed: {e}")

    def _trigger_self_restart(self, reason: str):
        """自己再起動をトリガー."""
        logger.error(f"🔄 Triggering self-restart: {reason}")

        self.stats["restart_count"] += 1
        self.stats["last_restart_time"] = time.time()

        # 再起動フラグを設定（メインループで検知される）
        if hasattr(self.camera_service, "_health_restart_requested"):
            self.camera_service._health_restart_requested = True

    def _trigger_camera_restart(self):
        """カメラのみを再起動."""
        try:
            logger.info("🔄 Restarting camera subsystem")

            if hasattr(self.camera_service, "picamera2"):
                picamera2 = self.camera_service.picamera2
                if picamera2:
                    picamera2.stop()
                    time.sleep(1)
                    picamera2.start()

            logger.info("✅ Camera subsystem restarted")

        except Exception as e:
            logger.error(f"Camera restart failed: {e}")
            self._trigger_self_restart("Camera restart failed")

    def get_health_stats(self) -> Dict[str, Any]:
        """健全性統計を取得."""
        return {
            **self.stats,
            "monitoring": self.monitoring,
            "uptime_seconds": time.time()
            - (self.stats["last_restart_time"] or time.time()),
        }
