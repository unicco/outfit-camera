#!/bin/bash
# カメラ問題診断スクリプト（Raspberry Pi 用）

echo "🔍 カメラサービス診断開始..."

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo "=== 1. 環境情報確認 ==="
echo "PWD: $(pwd)"
echo "USER: $USER"
echo "Python version: $(python3 --version)"
echo "System: $(uname -a)"

echo ""
echo "=== 2. ポート使用状況 ==="
for port in 8001 8035 8002 8003; do
    pids=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "Port $port: 使用中 (PIDs: $pids)"
        ps aux | grep -E "($pids)" | grep -v grep || true
    else
        echo "Port $port: 利用可能"
    fi
done

echo ""
echo "=== 3. カメラ関連プロセス ==="
ps aux | grep -E "(camera|uvicorn|python)" | grep -v grep || echo "関連プロセスなし"

echo ""
echo "=== 4. Picamera2 確認 ==="
python3 -c "
try:
    from picamera2 import Picamera2
    print('✅ Picamera2 import 成功')
    try:
        cameras = Picamera2.global_camera_info()
        print(f'📷 検出されたカメラ数: {len(cameras)}')
        for i, cam in enumerate(cameras):
            print(f'  Camera {i}: {cam}')
        if not cameras:
            print('❌ カメラが検出されません')
    except Exception as e:
        print(f'❌ カメラ検出エラー: {e}')
except ImportError as e:
    print(f'❌ Picamera2 import エラー: {e}')
    print('💡 システムPython で Picamera2 がインストールされていない可能性があります')
except Exception as e:
    print(f'❌ Picamera2 エラー: {e}')

# OpenCV でも確認
print()
try:
    import cv2
    print('✅ OpenCV import 成功')
    print(f'OpenCV version: {cv2.__version__}')
except ImportError as e:
    print(f'❌ OpenCV import エラー: {e}')
"

echo ""
echo "=== 5. SimpleCameraService ファイル確認 ==="
if [ -f "camera/camera_service.py" ]; then
    echo "✅ カメラサービスファイル存在"
    echo "ファイルサイズ: $(wc -c < camera/camera_service.py) bytes"
    echo "実行権限: $(ls -la camera/camera_service.py | cut -d' ' -f1)"
else
    echo "❌ SimpleCameraService ファイルが見つかりません"
fi

echo ""
echo "=== 6. 環境変数確認 ==="
echo "CAMERA_PORT: ${CAMERA_PORT:-未設定}"
echo "CAMERA_MODE: ${CAMERA_MODE:-未設定}"
echo "PHOTOS_DIR: ${PHOTOS_DIR:-未設定}"
echo "PIR_ENABLED: ${PIR_ENABLED:-未設定}"

echo ""
echo "=== 7. .env ファイル確認 ==="
if [ -f ".env" ]; then
    echo "✅ .env ファイル存在"
    echo "CAMERA関連設定:"
    grep -E "CAMERA|PIR" .env || echo "  CAMERA/PIR設定なし"
else
    echo "❌ .env ファイルが見つかりません"
fi

echo ""
echo "=== 8. photos ディレクトリ確認 ==="
if [ -d "photos" ]; then
    echo "✅ photos ディレクトリ存在"
    echo "ファイル数: $(ls photos 2>/dev/null | wc -l)"
    echo "権限: $(ls -ld photos | cut -d' ' -f1)"
else
    echo "❌ photos ディレクトリが見つかりません"
    echo "💡 作成中..."
    mkdir -p photos
    echo "✅ photos ディレクトリを作成しました"
fi

echo ""
echo "=== 9. ネットワーク接続確認 ==="
echo "localhost:8001 接続テスト:"
if curl -s -f "http://localhost:8001/health" > /dev/null 2>&1; then
    echo "✅ localhost:8001 で SimpleCameraService が応答"
    curl -s "http://localhost:8001/health"
else
    echo "❌ localhost:8001 で SimpleCameraService が応答しません"
fi

echo ""
echo "pi-camera.local:8001 接続テスト:"
if curl -s -f "http://pi-camera.local:8001/health" > /dev/null 2>&1; then
    echo "✅ pi-camera.local:8001 で SimpleCameraService が応答"
    curl -s "http://pi-camera.local:8001/health"
else
    echo "❌ pi-camera.local:8001 で SimpleCameraService が応答しません"
fi

echo ""
echo "=== 10. システムログ確認 ==="
if [ -f "/tmp/simple-camera-service.pid" ]; then
    PID=$(cat /tmp/simple-camera-service.pid)
    echo "記録されたPID: $PID"
    if ps -p $PID > /dev/null 2>&1; then
        echo "✅ プロセス $PID は実行中"
    else
        echo "❌ プロセス $PID は停止済"
    fi
else
    echo "⚠️  PIDファイルが見つかりません"
fi

echo ""
echo "=== 診断完了 ==="
echo "💡 次のステップ:"
echo "1. Picamera2 が利用できない場合 → sudo apt install python3-picamera2"
echo "2. SimpleCameraService を起動する場合 → ./scripts/debug/restart-camera-force.sh"
echo "3. 既存プロセスを停止する場合 → ./scripts/stop-all-camera.sh"
