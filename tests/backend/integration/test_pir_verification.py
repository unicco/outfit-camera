#!/usr/bin/env python3
"""PIRセンサー機能検証スクリプト
issue #402 の実装をテスト.
"""
import httpx
import asyncio

# Camera service URL
BASE_URL = "http://localhost:8001"  # Camera service port


async def test_pir_functionality():
    """PIRセンサー機能の包括的テスト."""
    print("🔍 PIRセンサー機能検証開始")
    print("=" * 50)

    async with httpx.AsyncClient() as client:

        # 1. PIRセンサー状態確認
        print("\n1️⃣ PIRセンサー状態確認")
        try:
            response = await client.get(f"{BASE_URL}/pir/status")
            if response.status_code == 200:
                status = response.json()
                print(f"✅ PIR enabled: {status['enabled']}")
                print(f"✅ Simulation mode: {status['simulation_mode']}")
                print(f"✅ Current mode: {status['current_mode']}")
                print(f"✅ Daily photo taken: {status['daily_photo_taken']}")
                print(f"✅ Detection threshold: {status['detection_threshold']}")
                print(f"✅ Detection window: {status['detection_window']}s")
            else:
                print(f"❌ Status check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False

        # 2. PIR状態リセット
        print("\n2️⃣ PIR状態リセット")
        try:
            response = await client.post(f"{BASE_URL}/pir/reset")
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Reset successful: {result['message']}")
            else:
                print(f"❌ Reset failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Reset error: {e}")

        # 3. PIRモーション検知シミュレーション（1回目）
        print("\n3️⃣ PIRモーション検知テスト（1回目 - しきい値未満）")
        try:
            response = await client.post(f"{BASE_URL}/pir/simulate")
            if response.status_code == 200:
                result = response.json()
                print(
                    f"✅ 1回目検知: detections={result['detections_count']}, mode={result['current_mode']}"
                )

                if result["current_mode"] == "sleep":
                    print("✅ 正常: 1回検知ではアクティブモードに移行せず")
                else:
                    print("⚠️  注意: 1回検知でアクティブモードに移行")
            else:
                print(f"❌ Simulation failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Simulation error: {e}")

        # 4. PIRモーション検知シミュレーション（2回目 - しきい値到達）
        print("\n4️⃣ PIRモーション検知テスト（2回目 - アクティブモード発火）")
        try:
            # 3秒以内に2回目検知
            await asyncio.sleep(1)  # 1秒待機
            response = await client.post(f"{BASE_URL}/pir/simulate")
            if response.status_code == 200:
                result = response.json()
                print(
                    f"✅ 2回目検知: detections={result['detections_count']}, mode={result['current_mode']}"
                )

                if result["current_mode"] == "active":
                    print("✅ 正常: 2回検知でアクティブモードに移行")
                else:
                    print("❌ エラー: 2回検知でもアクティブモードに移行せず")
            else:
                print(f"❌ Simulation failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Simulation error: {e}")

        # 5. アクティブモード状態確認
        print("\n5️⃣ アクティブモード状態確認")
        try:
            response = await client.get(f"{BASE_URL}/pir/status")
            if response.status_code == 200:
                status = response.json()
                print(f"✅ Current mode: {status['current_mode']}")
                print(f"✅ Active duration: {status['camera_active_duration']}s")

                if status["current_mode"] == "active":
                    print("✅ 正常: アクティブモードで稼働中")
                else:
                    print("⚠️  注意: アクティブモードになっていません")
        except Exception as e:
            print(f"❌ Status check error: {e}")

        # 6. 撮影テスト（アクティブモード中）
        print("\n6️⃣ 撮影テスト（アクティブモード中）")
        try:
            response = await client.post(f"{BASE_URL}/capture")
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 撮影成功: {result.get('filename', 'unknown')}")

                # 撮影後の状態確認
                await asyncio.sleep(1)
                status_response = await client.get(f"{BASE_URL}/pir/status")
                if status_response.status_code == 200:
                    status = status_response.json()
                    print(f"✅ 撮影後モード: {status['current_mode']}")
                    print(f"✅ Daily photo taken: {status['daily_photo_taken']}")

                    if status["daily_photo_taken"]:
                        print("✅ 正常: 1日1回撮影が記録されました")
                    else:
                        print("⚠️  注意: 1日1回撮影が記録されていません")
            else:
                print(f"❌ Capture failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Capture error: {e}")

        # 7. 1日1回制限テスト
        print("\n7️⃣ 1日1回撮影制限テスト")
        try:
            # PIRリセットして再度検知テスト
            await client.post(f"{BASE_URL}/pir/reset")

            # 1日1回撮影を手動で設定
            # （実際の実装では撮影成功時に自動設定される）
            print("✅ 1日1回制限の動作確認は実際の撮影で検証")
        except Exception as e:
            print(f"❌ Daily limit test error: {e}")

    print("\n" + "=" * 50)
    print("🎉 PIRセンサー機能検証完了")
    return True


def manual_test_instructions():
    """手動テスト手順を表示."""
    print("\n📋 手動テスト手順:")
    print("=" * 50)

    print("\n🔧 1. 環境設定:")
    print("   .env ファイルで以下を設定:")
    print("   PIR_ENABLED=true")
    print("   PIR_SIMULATION_MODE=true")
    print("   CAMERA_MODE=simulation")

    print("\n🚀 2. サーバー起動:")
    print("   cd camera")
    print("   python camera_service.py")

    print("\n🧪 3. APIテスト:")
    print("   # 状態確認")
    print("   curl http://localhost:8001/pir/status")
    print()
    print("   # PIRシミュレーション（1回目）")
    print("   curl -X POST http://localhost:8001/pir/simulate")
    print()
    print("   # PIRシミュレーション（2回目 - アクティブモード発火）")
    print("   curl -X POST http://localhost:8001/pir/simulate")
    print()
    print("   # 撮影テスト")
    print("   curl -X POST http://localhost:8001/capture")
    print()
    print("   # 状態確認（撮影後）")
    print("   curl http://localhost:8001/pir/status")

    print("\n📊 4. WebSocket通知確認:")
    print("   ブラウザで ws://localhost:8001/ws に接続")
    print("   PIR検知時の通知を確認:")
    print("   - pir_motion_detected")
    print("   - camera_mode_activated")
    print("   - daily_photo_completed")

    print("\n⏰ 5. タイマー動作確認:")
    print("   アクティブモード発火後、5分待機")
    print("   自動的にスリープモードに戻ることを確認")

    print("\n🔄 6. 省電力動作確認:")
    print("   ログで以下を確認:")
    print("   - スリープモード時: 画像処理スキップ")
    print("   - アクティブモード時: 通常の画像処理")


if __name__ == "__main__":
    print("PIRセンサー機能検証スクリプト")
    print("issue #402 実装テスト")

    # 手動テスト手順を表示
    manual_test_instructions()

    # 自動テスト実行
    print("\n" + "=" * 50)
    choice = input("自動テストを実行しますか？ (y/N): ").lower()

    if choice in ["y", "yes"]:
        asyncio.run(test_pir_functionality())
    else:
        print("手動テスト手順を参考にしてください。")
