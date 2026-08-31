#!/bin/bash

# Raspberry Pi 5 GPIO セットアップスクリプト
# PIR センサー用の GPIO ライブラリと設定を行います

set -euo pipefail

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Pi 5 検出
check_pi5() {
    info "ハードウェアを確認中..."
    if grep -q "Raspberry Pi 5" /proc/cpuinfo; then
        success "Raspberry Pi 5 が検出されました"
        return 0
    else
        warning "Raspberry Pi 5 以外のデバイスです。このスクリプトは Pi 5 用に最適化されています"
        read -p "続行しますか？ [y/N]: " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# GPIO ライブラリのインストール
install_gpio_libraries() {
    info "Pi 5 用 GPIO ライブラリをインストール中..."

    # システムパッケージのインストール
    sudo apt update
    sudo apt install -y python3-lgpio python3-gpiozero

    # pip でのバックアップインストール（システムパッケージが利用できない場合）
    if ! python3 -c "import lgpio" 2>/dev/null; then
        warning "システムパッケージの lgpio が利用できません。pip でインストールを試行します"
        warning "注意: Pi 5 環境では通常システムパッケージで十分です。pip インストールは最後の手段です"
        pip3 install --break-system-packages lgpio || {
            error "lgpio のインストールに失敗しました"
            exit 1
        }
    fi

    if ! python3 -c "import gpiozero" 2>/dev/null; then
        warning "システムパッケージの gpiozero が利用できません。pip でインストールを試行します"
        warning "注意: Pi 5 環境では通常システムパッケージで十分です。pip インストールは最後の手段です"
        pip3 install --break-system-packages gpiozero || {
            error "gpiozero のインストールに失敗しました"
            exit 1
        }
    fi

    success "GPIO ライブラリのインストール完了"
}

# GPIO グループの設定
setup_gpio_permissions() {
    info "GPIO アクセス権限を設定中..."

    # ユーザーを gpio グループに追加
    sudo usermod -a -G gpio,dialout "$USER"

    # udev ルールの設定（Pi 5 用）
    sudo tee /etc/udev/rules.d/99-gpio.rules > /dev/null << 'EOF'
# GPIO アクセス権限 (Raspberry Pi 5)
SUBSYSTEM=="gpio*", PROGRAM="/bin/sh -c 'chown -R root:gpio /sys/class/gpio && chmod -R 775 /sys/class/gpio; chown -R root:gpio /sys/devices/platform/soc/*.gpio/gpio && chmod -R 775 /sys/devices/platform/soc/*.gpio/gpio'"
KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"
KERNEL=="gpio*", GROUP="gpio", MODE="0660"
EOF

    sudo udevadm control --reload-rules
    sudo udevadm trigger

    success "GPIO アクセス権限の設定完了"
}

# GPIO テスト
test_gpio_setup() {
    info "GPIO セットアップをテスト中..."


    # lgpio テスト
    if python3 -c "import lgpio; chip = lgpio.gpiochip_open(0); print('lgpio chip 0 opened successfully'); lgpio.gpiochip_close(chip)" 2>/dev/null; then
        success "✅ lgpio テスト成功"
    else
        warning "⚠️ lgpio テストに失敗しました"
    fi


    # gpiozero テスト（Pi 5 対応）
    if python3 -c "
from gpiozero.pins.lgpio import LGPIOFactory
from gpiozero import Device
Device.pin_factory = LGPIOFactory(chip=0)
print('gpiozero with LGPIOFactory test successful')
" 2>/dev/null; then
        success "✅ gpiozero (Pi 5対応) テスト成功"
    else
        warning "⚠️ gpiozero Pi 5 対応テストに失敗しました"
    fi
}

# 環境変数の設定
setup_environment() {
    info "Pi 5 用環境変数を設定中..."


    # /etc/environment に GPIOZERO_PIN_FACTORY を追加
    if ! grep -q "GPIOZERO_PIN_FACTORY=lgpio" /etc/environment; then
        echo "GPIOZERO_PIN_FACTORY=lgpio" | sudo tee -a /etc/environment > /dev/null
        success "環境変数 GPIOZERO_PIN_FACTORY=lgpio を追加しました"
    else
        success "環境変数 GPIOZERO_PIN_FACTORY=lgpio は既に設定済です"
    fi


    # 現在のセッション用にエクスポート
    export GPIOZERO_PIN_FACTORY=lgpio
}

# systemd サービスの更新確認
check_systemd_service() {
    info "systemd サービスの Pi 5 対応を確認中..."

    SERVICE_FILE="/etc/systemd/system/coordinate-camera.service"

    if [[ -f "$SERVICE_FILE" ]]; then
        if grep -q "GPIOZERO_PIN_FACTORY=lgpio" "$SERVICE_FILE"; then
            success "✅ systemd サービスに Pi 5 GPIO 設定が適用済です"
        else
            warning "⚠️ systemd サービスに Pi 5 GPIO 設定が不足しています"
            info "以下の環境変数を coordinate-camera.service に追加してください："
            echo "Environment=\"GPIOZERO_PIN_FACTORY=lgpio\""
            echo "SupplementaryGroups=gpio video dialout"
        fi
    else
        info "systemd サービスファイルが見つかりません（まだインストールされていません）"
    fi
}

# メイン処理
main() {
    info "🔧 Raspberry Pi 5 GPIO セットアップを開始します"
    echo


    check_pi5
    install_gpio_libraries
    setup_gpio_permissions
    setup_environment
    test_gpio_setup
    check_systemd_service


    echo
    success "🎉 Pi 5 GPIO セットアップ完了！"
    echo
    info "📋 次のステップ:"
    echo "  1. シェルを再起動するか、ログアウト/ログインしてください"
    echo "  2. coordinate-camera サービスを再起動してください:"
    echo "     sudo systemctl restart coordinate-camera"
    echo "  3. PIR センサーの動作を確認してください"
    echo
    warning "⚠️ グループ変更を反映するため、ログアウト/ログインが必要です"
}

# スクリプト実行
main "$@"
