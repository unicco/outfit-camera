#!/bin/bash
# SimpleCameraService 起動スクリプト（Raspberry Pi 用）

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "🎥 SimpleCameraService 起動中..."

# 明示的にポート 8001 を設定
export CAMERA_PORT=8001

# 環境変数読み込み
if [ -f .env ]; then
    source .env
    echo "✅ .env ファイル読み込み完了"
else
    echo "⚠️  .env ファイルが見つかりません"
fi

# カメラポート設定
export CAMERA_PORT=8001

# 既存のカメラプロセスを停止（すべてのポート）
echo "🔄 既存のカメラプロセス停止..."
for port in 8001 8035 8002 8003; do
    pids=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "Port $port のプロセスを停止: $pids"
        echo "$pids" | xargs kill -TERM 2>/dev/null || true
        sleep 1
        # 強制終了
        remaining_pids=$(lsof -ti :$port 2>/dev/null || true)
        if [ -n "$remaining_pids" ]; then
            echo "$remaining_pids" | xargs kill -KILL 2>/dev/null || true
        fi
    fi
done

# 追加で camera_service プロセスを名前で停止
pkill -f camera_service || true
sleep 2

# SimpleCameraService をシステムPython で起動（Picamera2 アクセス）
echo "🚀 SimpleCameraService 起動 (システムPython)..."
echo "Port: $CAMERA_PORT"
echo "Photos directory: ${PHOTOS_DIR:-./photos}"

# 必要な環境変数をエクスポート
export PHOTOS_DIR="${PHOTOS_DIR:-./photos}"
export CAMERA_MODE="${CAMERA_MODE:-hardware}"
export PIR_ENABLED="${PIR_ENABLED:-true}"
export PIR_GPIO_PIN="${PIR_GPIO_PIN:-18}"

# システムPython で直接実行（venv は Picamera2 にアクセスできない）
python3 camera/camera_service.py &

CAMERA_PID=$!
echo "📋 Camera service PID: $CAMERA_PID"

# ヘルスチェック（最大30秒待機）
echo "🏥 ヘルスチェック実行中..."
for i in {1..6}; do
    sleep 5
    echo "ヘルスチェック試行 $i/6..."
    if curl -s "http://localhost:$CAMERA_PORT/health" | grep -q "healthy"; then
        echo "✅ SimpleCameraService 正常に起動しました"
        echo "📺 Stream: http://localhost:$CAMERA_PORT/stream"
        echo "📸 Capture: http://localhost:$CAMERA_PORT/capture"
        echo "🔌 WebSocket: ws://localhost:$CAMERA_PORT/ws"
        break
    elif [ $i -eq 6 ]; then
        echo "❌ ヘルスチェック失敗"
        echo "ログを確認してください"
        exit 1
    fi
done

echo ""
echo "🎯 サービス確認URL:"
echo "- Health: http://pi-camera.local:$CAMERA_PORT/health"
echo "- Status: http://pi-camera.local:$CAMERA_PORT/status"
echo "- Stream: http://pi-camera.local:$CAMERA_PORT/stream"
echo ""
echo "🛑 停止する場合: kill $CAMERA_PID"
echo "💾 PID $CAMERA_PID を記録しています"

# PIDを記録
echo $CAMERA_PID > /tmp/simple-camera-service.pid
