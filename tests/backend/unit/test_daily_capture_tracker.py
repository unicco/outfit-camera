"""DailyCaptureTracker のユニットテスト."""

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

# テスト用環境変数設定
os.environ["LOG_LEVEL"] = "WARNING"

from coordinate_recorder.daily_capture_tracker import DailyCaptureTracker


class TestDailyCaptureTracker:
    """DailyCaptureTracker のテストクラス."""

    @pytest.fixture
    def temp_dir(self):
        """テスト用の一時ディレクトリ."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def tracker(self, temp_dir):
        """テスト用のDailyCaptureTrackerインスタンス."""
        return DailyCaptureTracker(data_dir=temp_dir)

    def test_initialization_empty_state(self, temp_dir):
        """空の状態での初期化テスト."""
        tracker = DailyCaptureTracker(data_dir=temp_dir)

        assert tracker.state == {}
        assert tracker.data_dir == Path(temp_dir)
        assert tracker.state_file == Path(temp_dir) / "daily_capture_state.json"

    def test_initialization_with_existing_state(self, temp_dir):
        """既存状態ファイルがある場合の初期化テスト."""
        # 事前にデータを作成
        state_data = {
            "2024-06-15": {
                "captured": True,
                "captures": [
                    {
                        "photo_id": "existing-photo",
                        "timestamp": "2024-06-15T10:00:00",
                        "metadata": {},
                    }
                ],
                "last_capture": "2024-06-15T10:00:00",
            }
        }

        state_file = Path(temp_dir) / "daily_capture_state.json"
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        # トラッカー初期化
        tracker = DailyCaptureTracker(data_dir=temp_dir)

        assert "2024-06-15" in tracker.state
        assert tracker.state["2024-06-15"]["captured"] is True

    def test_mark_captured_today(self, tracker):
        """本日の撮影記録テスト."""
        # 初期状態：未撮影
        assert tracker.is_captured_today() is False

        # 撮影を記録
        tracker.mark_captured_today("photo-123", {"test": True})

        # 状態確認
        assert tracker.is_captured_today() is True

        today = date.today().isoformat()
        assert today in tracker.state
        assert tracker.state[today]["captured"] is True
        assert len(tracker.state[today]["captures"]) == 1

        capture = tracker.state[today]["captures"][0]
        assert capture["photo_id"] == "photo-123"
        assert capture["metadata"]["test"] is True

    def test_multiple_captures_same_day(self, tracker):
        """同日複数撮影のテスト."""
        # 1回目
        tracker.mark_captured_today("photo-1")
        assert tracker.get_capture_count_today() == 1

        # 2回目
        tracker.mark_captured_today("photo-2")
        assert tracker.get_capture_count_today() == 2

        # 状態確認
        captures = tracker.get_today_captures()
        assert len(captures) == 2
        assert captures[0]["photo_id"] == "photo-1"
        assert captures[1]["photo_id"] == "photo-2"

    def test_is_captured_today(self, tracker):
        """撮影済判定テスト."""
        # 初期状態：未撮影
        assert tracker.is_captured_today() is False

        # 撮影後：撮影済
        tracker.mark_captured_today("test-photo")
        assert tracker.is_captured_today() is True

    def test_get_today_captures(self, tracker):
        """本日の撮影記録取得テスト."""
        # 初期状態：空リスト
        assert tracker.get_today_captures() == []

        # 撮影記録
        tracker.mark_captured_today("photo-1", {"location": "entrance"})
        tracker.mark_captured_today("photo-2", {"location": "entrance"})

        captures = tracker.get_today_captures()
        assert len(captures) == 2
        assert captures[0]["photo_id"] == "photo-1"
        assert captures[0]["metadata"]["location"] == "entrance"

    def test_reset_today(self, tracker):
        """本日のリセットテスト."""
        # 撮影を記録
        tracker.mark_captured_today("photo-to-reset")
        assert tracker.is_captured_today() is True
        assert tracker.get_capture_count_today() == 1

        # リセット
        tracker.reset_today()

        # 状態確認
        assert tracker.is_captured_today() is False
        assert tracker.get_capture_count_today() == 0
        assert tracker.get_today_captures() == []

    def test_get_status(self, tracker):
        """ステータス取得テスト."""
        # 初期状態
        status = tracker.get_status()

        required_keys = [
            "date",
            "captured_today",
            "capture_count",
            "last_capture",
            "total_days_recorded",
        ]
        for key in required_keys:
            assert key in status

        assert status["captured_today"] is False
        assert status["capture_count"] == 0
        assert status["last_capture"] is None
        assert status["total_days_recorded"] == 0

        # 撮影後
        tracker.mark_captured_today("status-test-photo")
        status = tracker.get_status()

        assert status["captured_today"] is True
        assert status["capture_count"] == 1
        assert status["last_capture"] is not None
        assert status["total_days_recorded"] == 1

    def test_get_history(self, tracker):
        """履歴取得テスト."""
        # 過去のデータを手動で設定
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        two_days_ago = (date.today() - timedelta(days=2)).isoformat()

        tracker.state[yesterday] = {
            "captured": True,
            "captures": [
                {"photo_id": "yesterday-photo", "timestamp": "2024-06-14T10:00:00"}
            ],
            "last_capture": "2024-06-14T10:00:00",
        }

        tracker.state[two_days_ago] = {
            "captured": False,
            "captures": [],
        }

        # 今日の撮影
        tracker.mark_captured_today("today-photo")

        # 履歴取得（3日間）
        history = tracker.get_history(days=3)

        assert len(history) == 3

        # 今日
        today = date.today().isoformat()
        assert history[today]["captured"] is True
        assert history[today]["count"] == 1

        # 昨日
        assert history[yesterday]["captured"] is True
        assert history[yesterday]["count"] == 1

        # 2日前
        assert history[two_days_ago]["captured"] is False
        assert history[two_days_ago]["count"] == 0

    def test_cleanup_old_dates(self, tracker):
        """古いデータのクリーンアップテスト."""
        # 古いデータを設定
        old_date = (date.today() - timedelta(days=10)).isoformat()
        recent_date = (date.today() - timedelta(days=3)).isoformat()

        tracker.state[old_date] = {"captured": True, "captures": []}
        tracker.state[recent_date] = {"captured": True, "captures": []}

        # クリーンアップ実行（keep_days=7）
        tracker._cleanup_old_dates(keep_days=7)

        # 確認
        assert old_date not in tracker.state  # 10日前は削除される
        assert recent_date in tracker.state  # 3日前は残る

    def test_state_persistence(self, temp_dir):
        """状態の永続化テスト."""
        # インスタンス1で撮影記録
        tracker1 = DailyCaptureTracker(data_dir=temp_dir)
        tracker1.mark_captured_today("persistence-test-photo", {"persistent": True})

        # ファイルが作成されていることを確認
        state_file = Path(temp_dir) / "daily_capture_state.json"
        assert state_file.exists()

        # インスタンス2で読み込み
        tracker2 = DailyCaptureTracker(data_dir=temp_dir)

        # データが引き継がれていることを確認
        assert tracker2.is_captured_today() is True
        captures = tracker2.get_today_captures()
        assert len(captures) == 1
        assert captures[0]["photo_id"] == "persistence-test-photo"
        assert captures[0]["metadata"]["persistent"] is True

    def test_corrupted_state_file_handling(self, temp_dir):
        """破損したステートファイルの処理テスト."""
        # 破損したJSONファイルを作成
        state_file = Path(temp_dir) / "daily_capture_state.json"
        with open(state_file, "w") as f:
            f.write("invalid json content")

        # トラッカー初期化（エラーにならずに空の状態で開始）
        tracker = DailyCaptureTracker(data_dir=temp_dir)

        assert tracker.state == {}
        assert tracker.is_captured_today() is False

    def test_invalid_date_cleanup(self, tracker):
        """不正な日付形式のクリーンアップテスト."""
        # 不正な日付形式を設定
        tracker.state["invalid-date"] = {"captured": True}
        tracker.state["2024-13-99"] = {"captured": True}  # 不正な日付
        valid_date = date.today().isoformat()
        tracker.state[valid_date] = {"captured": True}

        # クリーンアップ実行
        tracker._cleanup_old_dates()

        # 不正な日付は削除され、正常な日付は残る
        assert "invalid-date" not in tracker.state
        assert "2024-13-99" not in tracker.state
        assert valid_date in tracker.state
