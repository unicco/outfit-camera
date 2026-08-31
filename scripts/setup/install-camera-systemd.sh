#!/bin/bash
# カメラサービスを systemd サービスとしてインストール

set -e

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# プロジェクトルート
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

print_status "🚀 カメラサービスの systemd インストールを開始します"

# 1. 既存のカメラプロセスを停止
print_status "既存のカメラプロセスを停止中..."
sudo systemctl stop coordinate-camera 2>/dev/null || true
pkill -f camera_service.py 2>/dev/null || true
sleep 2

# 2. ラッパースクリプトに実行権限を付与
print_status "ラッパースクリプトに実行権限を付与..."
chmod +x "$PROJECT_ROOT/scripts/systemd-camera-wrapper.sh"

# 3. systemd サービスファイルをコピー
print_status "systemd サービスファイルをインストール..."
sudo cp "$PROJECT_ROOT/systemd/coordinate-camera.service" /etc/systemd/system/

# 4. systemd の設定をリロード
print_status "systemd の設定をリロード..."
sudo systemctl daemon-reload

# 5. サービスを有効化（自動起動）
print_status "サービスの自動起動を有効化..."
sudo systemctl enable coordinate-camera

# 6. サービスを起動
print_status "サービスを起動..."
sudo systemctl start coordinate-camera

# 7. サービスの状態を確認
print_status "サービスの状態を確認..."
sleep 3
if sudo systemctl is-active --quiet coordinate-camera; then
    print_status "✅ カメラサービスが正常に起動しました"
    sudo systemctl status coordinate-camera --no-pager
else
    print_error "❌ カメラサービスの起動に失敗しました"
    sudo systemctl status coordinate-camera --no-pager
    exit 1
fi

# 8. Pi 5 GPIO 設定確認
print_status "Pi 5 GPIO 設定を確認中..."
if grep -q "Raspberry Pi 5" /proc/cpuinfo; then
    print_status "Raspberry Pi 5 が検出されました"

    # GPIO 設定の簡単な確認
    if grep -q "GPIOZERO_PIN_FACTORY=lgpio" /etc/systemd/system/coordinate-camera.service; then
        print_status "✅ systemd サービスに Pi 5 GPIO 設定が適用されています"
    else
        print_warning "⚠️ Pi 5 の GPIO 設定が必要です"
        print_status "📋 以下のコマンドで Pi 5 GPIO セットアップを実行してください:"
        echo "  ./scripts/setup/setup-pi5-gpio.sh"
        echo ""
    fi
fi

# 9. ヘルスチェック
print_status "ヘルスチェック実行中..."
sleep 3
if curl -s "http://localhost:8001/health" | grep -q "healthy"; then
    print_status "✅ ヘルスチェック成功"
    print_status "✅ 内蔵ヘルスモニタリング機能が有効化されました"
else
    print_warning "⚠️ ヘルスチェックに失敗しました（サービスはまだ起動中の可能性があります）"
fi

print_status "🔍 ヘルスモニタリング機能について:"
echo "  - HTTP health endpoint チェック"
echo "  - PIR センサー応答監視"
echo "  - カメラデバイス可用性確認"
echo "  - ポート 8001 待機状態チェック"
echo "  - 60秒毎の自動監視と異常時の自動復旧"

echo ""
print_status "📋 使用可能なコマンド:"
echo "  状態確認:     sudo systemctl status coordinate-camera"
echo "  起動:        sudo systemctl start coordinate-camera"
echo "  停止:        sudo systemctl stop coordinate-camera"
echo "  再起動:      sudo systemctl restart coordinate-camera"
echo "  ログ確認:     sudo journalctl -u coordinate-camera -f"
echo "  無効化:      sudo systemctl disable coordinate-camera"
echo ""
print_status "🎉 インストール完了！"
