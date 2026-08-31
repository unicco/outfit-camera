"""PIR センサーの日付切り替えロジックのテスト."""

from datetime import datetime, date
from unittest.mock import Mock, patch
import sys
from pathlib import Path

import pytest

# src ディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from coordinate_recorder.date_utils import get_effective_date

# camera_service が picamera2 を import できる環境（実機 Pi）でのみ、Picamera2 を
# patch するセンサーテストを実行する。非 Pi では Picamera2 名前が存在せず patch が
# AttributeError になるため skip する。
from camera import camera_service

requires_picamera2 = pytest.mark.skipif(
    not camera_service.PICAMERA2_AVAILABLE,
    reason="Picamera2 not available (non-Pi environment)",
)


@requires_picamera2
def test_pir_sensor_disabled_after_5pm_with_photo():
    """当日撮影済なら _is_daily_photo_completed が True を返す（撮影はスキップ）.

    注: 画面点灯は日次撮影の完了状態から独立している。この判定が
    ガードするのは撮影であって、PIR による画面点灯ではない。
    """
    # カメラサービスの初期化をモック化
    with patch("camera.camera_service.Picamera2", Mock()):
        with patch("camera.camera_service.MotionSensor", Mock()):
            # API レスポンスをモック化
            with patch("requests.get") as mock_get:
                # 午後8時に設定
                test_time = datetime(2025, 8, 20, 20, 0, 0)

                # API が「すでに撮影済」を返す
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "already_captured": True,
                    "capture_required": False,
                }
                mock_get.return_value = mock_response

                # CameraService をインポート（ここでモックが適用される）
                from camera.camera_service import CameraService

                with patch("camera.camera_service.datetime") as mock_datetime:
                    mock_datetime.now.return_value = test_time
                    mock_datetime.side_effect = lambda *args, **kw: datetime(
                        *args, **kw
                    )

                    # カメラサービスを初期化
                    camera = CameraService()

                    # 日付チェック
                    is_completed = camera._is_daily_photo_completed()

                    # 8月20日の午後8時は、翌日（8月21日）扱いとなる
                    # API が撮影済を返すので当日撮影は完了扱い（撮影はスキップ）
                    assert is_completed is True


@requires_picamera2
def test_pir_sensor_enabled_before_5pm_without_photo():
    """当日未撮影なら _is_daily_photo_completed が False を返す（撮影が必要）."""
    with patch("camera.camera_service.Picamera2", Mock()):
        with patch("camera.camera_service.MotionSensor", Mock()):
            with patch("requests.get") as mock_get:
                # 午後3時に設定
                test_time = datetime(2025, 8, 20, 15, 0, 0)

                # API が「撮影が必要」を返す
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "already_captured": False,
                    "capture_required": True,
                }
                mock_get.return_value = mock_response

                from camera.camera_service import CameraService

                with patch("camera.camera_service.datetime") as mock_datetime:
                    mock_datetime.now.return_value = test_time
                    mock_datetime.side_effect = lambda *args, **kw: datetime(
                        *args, **kw
                    )

                    camera = CameraService()
                    is_completed = camera._is_daily_photo_completed()

                    # 当日未撮影なので撮影が必要
                    assert is_completed is False


@requires_picamera2
def test_pir_wakes_display_even_after_daily_photo():
    """当日撮影済でも PIR 検知で画面が点灯する（リグレッション）.

    点灯を日次撮影の完了状態から切り離した修正の回帰防止。
    _is_daily_photo_completed() が True でも _on_pir_motion が
    turn_on_display() を呼ぶことを検証する。
    """
    with patch("camera.camera_service.Picamera2", Mock()):
        with patch("camera.camera_service.MotionSensor", Mock()):
            with patch("requests.get") as mock_get:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "already_captured": True,
                    "capture_required": False,
                }
                mock_get.return_value = mock_response

                from camera.camera_service import CameraService

                camera = CameraService()
                # 当日撮影済でも点灯すること（撮影ガードから独立）
                camera._is_daily_photo_completed = Mock(return_value=True)
                camera.turn_on_display = Mock(return_value=True)
                camera._update_pir_activity = Mock()
                camera.display_state = "off"
                # しきい値を 1 にして単一検知でしきい値到達させる
                camera.pir_detection_threshold = 1

                camera._on_pir_motion()

                camera.turn_on_display.assert_called_once()


def test_date_reset_at_7am():
    """午前7時を境に実効日付が切り替わることを確認.

    get_effective_date は cutoff_hour=7（午前7時）で日付を切り替える。
    7時より前は前日扱い、7時以降は当日扱い。
    """
    # 8月20日午前6時59分（切り替え前 → 前日扱い）
    before_7am = datetime(2025, 8, 20, 6, 59, 0)
    assert get_effective_date(before_7am) == date(2025, 8, 19)

    # 8月20日午前7時0分（切り替え後 → 当日扱い）
    after_7am = datetime(2025, 8, 20, 7, 0, 0)
    assert get_effective_date(after_7am) == date(2025, 8, 20)
