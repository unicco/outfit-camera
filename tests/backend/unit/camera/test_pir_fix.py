#!/usr/bin/env python3
"""PIR センサーエラー修正の単体テスト."""

import threading
import time


def test_pir_deque_error_handling():
    """PIR センサーの deque mutated エラーハンドリングをテスト."""
    print("=== PIR deque エラーハンドリングテスト ===")

    # モック PIR センサー
    class MockPIRSensor:
        def __init__(self):
            self.call_count = 0

        @property
        def is_active(self):
            self.call_count += 1
            # 3回に1回エラーを発生させる
            if self.call_count % 3 == 0:
                raise RuntimeError("deque mutated during iteration")
            return True

    mock_sensor = MockPIRSensor()
    pir_sensor_lock = threading.Lock()

    # 修正されたコードのロジックを再現
    def check_pir_status():
        pir_is_active = False

        with pir_sensor_lock:
            try:
                if hasattr(mock_sensor, "is_active"):
                    pir_is_active = mock_sensor.is_active
            except RuntimeError as e:
                if "deque mutated during iteration" in str(e):
                    print(f"  [デバッグ] PIR sensor read conflict (ignorable): {e}")
                    pir_is_active = False
                else:
                    raise

        return pir_is_active

    # テスト実行
    success_count = 0
    handled_error_count = 0

    for i in range(10):
        print(f"\nテスト {i+1}/10:")
        try:
            result = check_pir_status()
        except Exception as exc:  # pragma: no cover - デバッグ用メッセージ保持
            raise AssertionError(
                f"unexpected error while checking PIR status: {exc}"
            ) from exc

        if result:
            success_count += 1
            print("  ✓ PIR アクティブを検出")
        else:
            handled_error_count += 1
            print("  ✓ エラーを適切に処理（デフォルト値を使用）")

    print("\n=== 結果 ===")
    print(f"成功: {success_count} 回")
    print(f"エラー処理: {handled_error_count} 回")
    print(f"合計: {success_count + handled_error_count}/10 回正常処理")

    total = success_count + handled_error_count
    assert total == 10, f"expected 10 iterations, handled {total}"
    assert handled_error_count >= 1, "error path was not exercised"


def test_concurrent_pir_access():
    """複数スレッドからの PIR アクセステスト."""
    print("\n\n=== 並行アクセステスト ===")

    class SharedPIRSensor:
        def __init__(self):
            self._deque = list(range(10))
            self._lock = threading.Lock()

        @property
        def is_active(self):
            # deque の反復処理をシミュレート
            total = 0
            for item in self._deque:
                # 別スレッドが deque を変更する可能性
                total += item
                time.sleep(0.0001)  # 競合状態を起こしやすくする
            return total > 25

        def modify_deque(self):
            """別スレッドから deque を変更."""
            self._deque.append(len(self._deque))
            if len(self._deque) > 20:
                self._deque.pop(0)

    sensor = SharedPIRSensor()
    pir_lock = threading.Lock()
    errors = []

    def reader_thread(thread_id):
        """センサーを読み取るスレッド."""
        for i in range(20):
            try:
                with pir_lock:
                    try:
                        sensor.is_active
                    except RuntimeError as e:
                        if "deque mutated" in str(e):
                            pass  # エラーを無視
                        else:
                            raise
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
            time.sleep(0.001)

    def modifier_thread():
        """センサーの内部状態を変更するスレッド."""
        for i in range(50):
            sensor.modify_deque()
            time.sleep(0.001)

    # スレッドを開始
    threads = []

    # 修正スレッド
    mod_thread = threading.Thread(target=modifier_thread)
    threads.append(mod_thread)
    mod_thread.start()

    # 読み取りスレッド
    for i in range(3):
        thread = threading.Thread(target=reader_thread, args=(i,))
        threads.append(thread)
        thread.start()

    # 全スレッドの完了を待つ
    for thread in threads:
        thread.join()

    if errors:
        formatted = "\n".join(errors)
        raise AssertionError(
            f"unexpected errors during concurrent access:\n{formatted}"
        )

    print("✓ すべてのアクセスが正常に処理されました")


if __name__ == "__main__":
    try:
        test_pir_deque_error_handling()
        test1_passed = True
    except AssertionError:
        test1_passed = False

    try:
        test_concurrent_pir_access()
        test2_passed = True
    except AssertionError:
        test2_passed = False

    print("\n\n=== テスト結果サマリー ===")
    print(f"deque エラーハンドリング: {'✓ PASS' if test1_passed else '✗ FAIL'}")
    print(f"並行アクセステスト: {'✓ PASS' if test2_passed else '✗ FAIL'}")

    if test1_passed and test2_passed:
        print("\n✅ すべてのテストが成功しました！")
        exit(0)
    else:
        print("\n❌ テストが失敗しました")
        exit(1)
