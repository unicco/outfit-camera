#!/bin/bash

# Cloudflared インストールスクリプト
# Raspberry Pi での Cloudflare Tunnel 設定用

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

# OS アーキテクチャ検出
detect_architecture() {
    local arch=$(uname -m)
    case $arch in
        x86_64)
            echo "amd64"
            ;;
        aarch64|arm64)
            echo "arm64"
            ;;
        armv7l|armv6l)
            echo "arm"
            ;;
        *)
            log_error "サポートされていないアーキテクチャ: $arch"
            exit 1
            ;;
    esac
}

# Cloudflared のダウンロードとインストール
install_cloudflared() {
    local arch=$(detect_architecture)
    local version="latest"
    local download_url="https://github.com/cloudflare/cloudflared/releases/${version}/download/cloudflared-linux-${arch}"

    log_info "Cloudflared をダウンロードしています... (アーキテクチャ: $arch)"

    # 一時ディレクトリでダウンロード
    local temp_dir=$(mktemp -d)
    local temp_file="$temp_dir/cloudflared"

    if ! curl -L -o "$temp_file" "$download_url"; then
        log_error "Cloudflared のダウンロードに失敗しました"
        rm -rf "$temp_dir"
        exit 1
    fi

    # 実行権限を付与
    chmod +x "$temp_file"

    # /usr/local/bin にインストール
    if sudo mv "$temp_file" /usr/local/bin/cloudflared; then
        log_success "Cloudflared を /usr/local/bin/ にインストールしました"
    else
        log_error "Cloudflared のインストールに失敗しました"
        rm -rf "$temp_dir"
        exit 1
    fi

    # 一時ディレクトリを削除
    rm -rf "$temp_dir"
}

# インストール確認
verify_installation() {
    log_info "インストールを確認しています..."

    if command -v cloudflared >/dev/null 2>&1; then
        local version=$(cloudflared version 2>/dev/null || echo "バージョン情報取得不可")
        log_success "Cloudflared が正常にインストールされました"
        log_info "バージョン: $version"
        return 0
    else
        log_error "Cloudflared のインストール確認に失敗しました"
        return 1
    fi
}

# 設定ディレクトリ準備
setup_config_directory() {
    local config_dir="/etc/cloudflared"

    log_info "設定ディレクトリを準備しています..."

    if sudo mkdir -p "$config_dir"; then
        sudo chown cloudflared:cloudflared "$config_dir" 2>/dev/null || true
        sudo chmod 755 "$config_dir"
        log_success "設定ディレクトリを作成しました: $config_dir"
    else
        log_error "設定ディレクトリの作成に失敗しました"
        exit 1
    fi
}

# cloudflared ユーザー作成
create_cloudflared_user() {
    log_info "cloudflared ユーザーを作成しています..."

    if id "cloudflared" >/dev/null 2>&1; then
        log_warning "cloudflared ユーザーは既に存在します"
    else
        if sudo useradd -r -s /usr/sbin/nologin cloudflared; then
            log_success "cloudflared ユーザーを作成しました"
        else
            log_error "cloudflared ユーザーの作成に失敗しました"
            exit 1
        fi
    fi
}

# メイン処理
main() {
    log_info "Cloudflared インストールを開始します..."

    # 既存インストールの確認
    if command -v cloudflared >/dev/null 2>&1; then
        log_warning "Cloudflared は既にインストールされています"
        local current_version=$(cloudflared version 2>/dev/null || echo "不明")
        log_info "現在のバージョン: $current_version"

        read -p "再インストールしますか？ (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "インストールをキャンセルしました"
            exit 0
        fi
    fi

    # 必要なパッケージの確認
    if ! command -v curl >/dev/null 2>&1; then
        log_info "curl をインストールしています..."
        sudo apt-get update && sudo apt-get install -y curl
    fi

    # インストール実行
    install_cloudflared
    create_cloudflared_user
    setup_config_directory

    # 確認
    if verify_installation; then
        log_success "Cloudflared のインストールが完了しました！"
        echo ""
        log_info "次の手順:"
        log_info "1. Cloudflare にログインして tunnel を作成"
        log_info "2. 認証情報を設定"
        log_info "3. 設定ファイルを作成"
        log_info "4. systemd サービスを設定"
        echo ""
        log_info "詳細は setup-cloudflare-tunnel.sh を実行してください"
    else
        log_error "インストールに問題があります"
        exit 1
    fi
}

# スクリプト実行
main "$@"
