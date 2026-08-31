#!/bin/bash

# Cloudflare Tunnel systemd サービス設定スクリプト

set -euo pipefail

# カラー出力設定
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ログ関数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 設定変数
SERVICE_NAME="cloudflare-tunnel"
SERVICE_FILE="cloudflare-tunnel.service"
SYSTEMD_DIR="/etc/systemd/system"
CONFIG_DIR="/etc/cloudflared"
HOME_DIR="/var/lib/cloudflared"

# 前提条件チェック
check_prerequisites() {
    log_info "前提条件をチェックしています..."

    # cloudflared の確認
    if ! command -v cloudflared >/dev/null 2>&1; then
        log_error "cloudflared がインストールされていません"
        exit 1
    fi

    # 設定ファイルの確認
    if [ ! -f "$CONFIG_DIR/config.yml" ]; then
        log_error "Cloudflare Tunnel 設定ファイルが見つかりません: $CONFIG_DIR/config.yml"
        log_info "先に setup-cloudflare-tunnel.sh を実行してください"
        exit 1
    fi

    # cloudflared ユーザーの確認
    if ! id "cloudflared" >/dev/null 2>&1; then
        log_error "cloudflared ユーザーが存在しません"
        exit 1
    fi

    log_success "前提条件チェック完了"
}

# cloudflared ユーザーのホームディレクトリ作成
setup_user_home() {
    log_info "cloudflared ユーザーのホームディレクトリを設定しています..."

    if [ ! -d "$HOME_DIR" ]; then
        sudo mkdir -p "$HOME_DIR"
        sudo chown cloudflared:cloudflared "$HOME_DIR"
        sudo chmod 750 "$HOME_DIR"
        log_success "ホームディレクトリを作成しました: $HOME_DIR"
    else
        log_info "ホームディレクトリは既に存在します: $HOME_DIR"
    fi
}

# systemd サービスファイルのコピー
install_service_file() {
    log_info "systemd サービスファイルをインストールしています..."

    local source_file="$(dirname "$0")/$SERVICE_FILE"
    local target_file="$SYSTEMD_DIR/$SERVICE_NAME.service"

    if [ ! -f "$source_file" ]; then
        log_error "サービスファイルが見つかりません: $source_file"
        exit 1
    fi

    # サービスファイルをコピー
    sudo cp "$source_file" "$target_file"
    sudo chmod 644 "$target_file"

    log_success "サービスファイルをインストールしました: $target_file"
}

# systemd デーモンリロード
reload_systemd() {
    log_info "systemd 設定をリロードしています..."

    if sudo systemctl daemon-reload; then
        log_success "systemd 設定をリロードしました"
    else
        log_error "systemd 設定のリロードに失敗しました"
        exit 1
    fi
}

# サービス有効化
enable_service() {
    log_info "Cloudflare Tunnel サービスを有効化しています..."

    if sudo systemctl enable "$SERVICE_NAME"; then
        log_success "サービスを有効化しました"
    else
        log_error "サービスの有効化に失敗しました"
        exit 1
    fi
}

# サービス開始
start_service() {
    log_info "Cloudflare Tunnel サービスを開始しています..."

    if sudo systemctl start "$SERVICE_NAME"; then
        log_success "サービスを開始しました"
    else
        log_error "サービスの開始に失敗しました"
        log_info "ログを確認してください: sudo journalctl -u $SERVICE_NAME -f"
        exit 1
    fi
}

# サービス状態確認
check_service_status() {
    log_info "サービス状態を確認しています..."

    sleep 3

    if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Cloudflare Tunnel サービスは正常に動作中です"

        # 詳細状態表示
        echo ""
        log_info "サービス詳細:"
        sudo systemctl status "$SERVICE_NAME" --no-pager -l

    else
        log_error "サービスが正常に開始されていません"
        echo ""
        log_info "エラーログ:"
        sudo journalctl -u "$SERVICE_NAME" -n 20 --no-pager
        exit 1
    fi
}

# 使用方法表示
show_usage() {
    echo ""
    log_success "Cloudflare Tunnel systemd サービスの設定が完了しました！"
    echo ""
    log_info "サービス管理コマンド:"
    log_info "- 状態確認: sudo systemctl status $SERVICE_NAME"
    log_info "- 開始: sudo systemctl start $SERVICE_NAME"
    log_info "- 停止: sudo systemctl stop $SERVICE_NAME"
    log_info "- 再起動: sudo systemctl restart $SERVICE_NAME"
    log_info "- ログ確認: sudo journalctl -u $SERVICE_NAME -f"
    echo ""
    log_info "次の手順:"
    log_info "1. Cloudflare Access で認証設定を行う"
    log_info "2. 外部ネットワークからアクセステストを実行"
    echo ""
}

# メイン処理
main() {
    log_info "Cloudflare Tunnel systemd サービス設定を開始します..."
    echo ""

    check_prerequisites
    setup_user_home
    install_service_file
    reload_systemd
    enable_service
    start_service
    check_service_status
    show_usage

    log_success "systemd サービスの設定が完了しました！"
}

# スクリプト実行
main "$@"
