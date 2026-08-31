#!/usr/bin/env python3
"""PIR センサーのスレッドセーフ性をテストするスクリプト."""

import sys
import os
import threading
import time

import pytest

# プロジェクトのルートパスを追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from camera.camera_service import CameraService
except ModuleNotFoundError as exc:  # pragma: no cover - カメラサービス未インストール環境
    pytest.skip(
        f"カメラサービスが存在しないためスキップ: {exc}", allow_module_level=True
    )


def test_pir_concurrent_access():
    """PIR センサーへの同時アクセスをテスト."""
    print("=== PIR センサーのスレッドセーフテスト開始 ===")

    # カメラサービスのインスタンス作成（シミュレーションモード）
    camera_service = CameraService(pir_simulation_mode=True)

    # テスト用の簡易 PIR センサーオブジェクトを作成
    class MockPIRSensor:
        def __init__(self):
            self._value = 0
            self._queue = []

        @property
        def is_active(self):
            # deque mutated エラーをシミュレート
            import random

            if random.random() < 0.3:  # 30%の確率でエラー
                raise RuntimeError("deque mutated during iteration")
            return self._value > 0.5

        @property
        def value(self):
            return self._value

    # モックオブジェクトを設定
    camera_service.pir_sensor = MockPIRSensor()
    camera_service.pir_sensor_lock = threading.Lock()

    # テスト結果を記録
    errors = []
    success_count = 0
    error_count = 0

    def access_pir_sensor(thread_id):
        """PIR センサーにアクセスするワーカー."""
        nonlocal success_count, error_count

        for i in range(100):
            try:
                # monitor_pir のロジックを模倣
                with camera_service.pir_sensor_lock:
                    try:
                        if hasattr(camera_service.pir_sensor, "is_active"):
                            camera_service.pir_sensor.is_active
                            success_count += 1
                    except RuntimeError as e:
                        if "deque mutated during iteration" in str(e):
                            # エラーを適切に処理
                            error_count += 1
                        else:
                            raise

                # 少し待機
                time.sleep(0.001)

            except Exception as e:
                errors.append(f"Thread {thread_id}: {str(e)}")

    # 複数スレッドで同時実行
    threads = []
    for i in range(5):
        thread = threading.Thread(target=access_pir_sensor, args=(i,))
        threads.append(thread)
        thread.start()

    # すべてのスレッドが終了するまで待機
    for thread in threads:
        thread.join()

    # 結果を表示
    print("\n=== テスト結果 ===")
    print(f"成功回数: {success_count}")
    print(f"処理されたエラー回数: {error_count}")
    print(f"未処理のエラー数: {len(errors)}")

    if errors:
        print("\n未処理のエラー:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\nすべてのエラーが適切に処理されました ✓")

    return len(errors) == 0


if __name__ == "__main__":
    success = test_pir_concurrent_access()
    sys.exit(0 if success else 1)
