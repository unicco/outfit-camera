"""日次撮影状況トラッカー
Issue #36 Phase 2: その日に既に撮影済かどうかを管理.
"""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from .logging_utils import log_with_context, setup_logging

logger = setup_logging(
    service_name="daily_tracker",
    component="capture",
    log_level=os.getenv("LOG_LEVEL", "INFO"),
)


class DailyCaptureTracker:
    """日次の撮影状況を追跡・管理するクラス.

    シンプルなファイルベースの実装で、その日に撮影が完了したかを記録。
    将来的にはデータベースに移行可能な設計。
    """

    def __init__(self, data_dir: str = "data"):
        """DailyCaptureTrackerの初期化.

        Args:
            data_dir: データ保存ディレクトリ

        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.state_file = self.data_dir / "daily_capture_state.json"

        # 状態を初期化またはロード
        self._load_state()

        logger.info(f"DailyCaptureTracker initialized with data_dir: {data_dir}")

    def _load_state(self) -> None:
        """保存された状態をロード."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    self.state = json.load(f)
                logger.info(f"Loaded existing state from {self.state_file}")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
                self.state = {}
        else:
            self.state = {}
            logger.info("Initialized empty state")

    def _save_state(self) -> None:
        """状態をファイルに保存."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            logger.debug("State saved successfully")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def mark_captured_today(self, photo_id: str, metadata: dict | None = None) -> None:
        """今日の撮影を記録.

        Args:
            photo_id: 撮影された写真のID
            metadata: 追加のメタデータ（オプション）

        """
        today = date.today().isoformat()

        if today not in self.state:
            self.state[today] = {"captured": False, "captures": []}

        capture_info = {
            "photo_id": photo_id,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        self.state[today]["captured"] = True
        self.state[today]["captures"].append(capture_info)
        self.state[today]["last_capture"] = capture_info["timestamp"]

        self._save_state()

        log_with_context(
            logger,
            "info",
            f"Marked capture for today: {photo_id}",
            date=today,
            photo_id=photo_id,
            capture_count=len(self.state[today]["captures"]),
            event_type="capture_marked",
        )

    def is_captured_today(self) -> bool:
        """今日既に撮影済かどうかを確認.

        Returns:
            撮影済の場合True

        """
        today = date.today().isoformat()

        # 日付が変わった場合の自動リセット
        self._cleanup_old_dates()

        is_captured = self.state.get(today, {}).get("captured", False)

        log_with_context(
            logger,
            "debug",
            f"Checked capture status for today: {is_captured}",
            date=today,
            is_captured=is_captured,
            event_type="status_check",
        )

        return bool(is_captured)

    def get_today_captures(self) -> list[dict]:
        """今日の撮影記録を取得.

        Returns:
            撮影記録のリスト

        """
        today = date.today().isoformat()
        captures = self.state.get(today, {}).get("captures", [])
        return list(captures)

    def get_capture_count_today(self) -> int:
        """今日の撮影回数を取得.

        Returns:
            撮影回数

        """
        return len(self.get_today_captures())

    def reset_today(self) -> None:
        """今日の撮影記録をリセット."""
        today = date.today().isoformat()

        if today in self.state:
            previous_count = len(self.state[today].get("captures", []))
            del self.state[today]
            self._save_state()

            log_with_context(
                logger,
                "info",
                "Reset today's capture records",
                date=today,
                previous_count=previous_count,
                event_type="daily_reset",
            )

    def _cleanup_old_dates(self, keep_days: int = 7) -> None:
        """古い日付のデータをクリーンアップ.

        Args:
            keep_days: 保持する日数

        """
        today = date.today()
        cleaned_count = 0

        for date_str in list(self.state.keys()):
            try:
                record_date = date.fromisoformat(date_str)
                if (today - record_date).days > keep_days:
                    del self.state[date_str]
                    cleaned_count += 1
            except ValueError:
                # 不正な日付形式は削除
                del self.state[date_str]
                cleaned_count += 1

        if cleaned_count > 0:
            self._save_state()
            logger.info(f"Cleaned up {cleaned_count} old date records")

    def get_status(self) -> dict:
        """現在の状態を取得.

        Returns:
            状態情報の辞書

        """
        today = date.today().isoformat()
        today_data = self.state.get(today, {})

        return {
            "date": today,
            "captured_today": today_data.get("captured", False),
            "capture_count": len(today_data.get("captures", [])),
            "last_capture": today_data.get("last_capture"),
            "total_days_recorded": len(self.state),
        }

    def get_history(self, days: int = 7) -> dict:
        """過去の撮影履歴を取得.

        Args:
            days: 取得する日数

        Returns:
            日付をキーとした撮影履歴

        """
        history = {}
        today = date.today()

        for i in range(days):
            check_date = today - timedelta(days=i)
            date_str = check_date.isoformat()

            if date_str in self.state:
                history[date_str] = {
                    "captured": self.state[date_str].get("captured", False),
                    "count": len(self.state[date_str].get("captures", [])),
                    "last_capture": self.state[date_str].get("last_capture"),
                }
            else:
                history[date_str] = {
                    "captured": False,
                    "count": 0,
                    "last_capture": None,
                }

        return history
