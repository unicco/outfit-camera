#!/bin/bash
# カメラサービス強制再起動スクリプト（Raspberry Pi 用）

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🔄 カメラサービス強制再起動中..."

# Step 1: すべてのカメラ関連プロセスを強制停止
echo "🛑 すべてのカメラプロセスを強制停止..."

# ポート番号でプロセスを停止
for port in 8001 8035 8002 8003 8004 8005; do
    pids=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "  📍 Port $port で動作中のプロセスを停止: $pids"
        echo "$pids" | xargs kill -KILL 2>/dev/null || true
    fi
done

# プロセス名で停止
echo "  📍 プロセス名による停止..."
pkill -9 -f camera_service || true
pkill -9 -f uvicorn || true

# Python プロセスで camera を含むものを停止
pgrep -f "python.*camera" | xargs kill -9 2>/dev/null || true

sleep 3

# Step 2: ポートが完全に解放されるまで待機
echo "🕐 ポート解放確認中..."
for i in {1..10}; do
    if ! lsof -i :8001 > /dev/null 2>&1; then
        echo "✅ ポート 8001 が解放されました"
        break
    else
        echo "  ⏳ ポート 8001 解放待機中... ($i/10)"
        sleep 1
    fi
    if [ $i -eq 10 ]; then
        echo "❌ ポート 8001 の解放に失敗しました"
        lsof -i :8001 || true
        exit 1
    fi
done

# Step 3: SimpleCameraService を起動
echo "🚀 SimpleCameraService 起動..."

# 環境変数を明示的に設定
export CAMERA_PORT=8001
export PHOTOS_DIR="$PROJECT_ROOT/photos"
export CAMERA_MODE=hardware
export PIR_ENABLED=true
export PIR_GPIO_PIN=18

# photos ディレクトリ作成
mkdir -p "$PHOTOS_DIR"

echo "🔧 設定確認:"
echo "  - Port: $CAMERA_PORT"
echo "  - Photos Dir: $PHOTOS_DIR"
echo "  - Camera Mode: $CAMERA_MODE"
echo "  - PIR Enabled: $PIR_ENABLED"

# システムPython で起動
echo "🐍 システムPython で SimpleCameraService 起動中..."
python3 camera/camera_service.py &

CAMERA_PID=$!
echo "📋 SimpleCameraService PID: $CAMERA_PID"

# Step 4: 起動確認
echo "🏥 起動確認中..."
for i in {1..12}; do
    sleep 5
    echo "  ⏳ 起動確認 $i/12..."

    if curl -s -f "http://localhost:8001/health" > /dev/null 2>&1; then
        echo "✅ SimpleCameraService が正常に起動しました！"

        # 詳細確認
        echo ""
        echo "📊 サービス状態:"
        curl -s "http://localhost:8001/health" || echo "  ❌ Health check failed"
        echo ""

        # ストリーム確認
        echo "📺 ストリーム確認:"
        if curl -s -I "http://localhost:8001/stream" | grep -q "200 OK"; then
            echo "  ✅ ストリーム利用可能"
        else
            echo "  ❌ ストリーム不可"
        fi

        echo ""
        echo "🎯 アクセスURL:"
        echo "  - Health: http://pi-camera.local:8001/health"
        echo "  - Stream: http://pi-camera.local:8001/stream"
        echo "  - Capture: http://pi-camera.local:8001/capture"
        echo "  - WebSocket: ws://pi-camera.local:8001/ws"
        echo ""
        echo "🛑 停止: kill $CAMERA_PID"

        # PID記録
        echo $CAMERA_PID > /tmp/simple-camera-service.pid

        exit 0
    elif [ $i -eq 12 ]; then
        echo "❌ SimpleCameraService の起動に失敗しました"
        echo "プロセス確認:"
        ps aux | grep $CAMERA_PID || echo "プロセスが見つかりません"
        exit 1
    fi
done
