#!/bin/bash

# Cloudflare Tunnel 設定スクリプト
# coordinate-recorder 用外部アクセス設定

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
TUNNEL_NAME="coordinate-recorder"
CONFIG_DIR="/etc/cloudflared"
CONFIG_FILE="$CONFIG_DIR/config.yml"
CREDENTIALS_FILE="$CONFIG_DIR/$TUNNEL_NAME.json"

# 環境変数から取得（デフォルト値設定）
UI_PORT="${UI_PORT:-3000}"
API_PORT="${API_PORT:-8000}"
CAMERA_PORT="${CAMERA_PORT:-8001}"
DOMAIN="${CLOUDFLARE_DOMAIN:-}"

# 前提条件チェック
check_prerequisites() {
    log_info "前提条件をチェックしています..."

    # cloudflared コマンドの確認
    if ! command -v cloudflared >/dev/null 2>&1; then
        log_error "cloudflared がインストールされていません"
        log_info "先に scripts/setup/install-cloudflared.sh を実行してください"
        exit 1
    fi

    # 設定ディレクトリの確認
    if [ ! -d "$CONFIG_DIR" ]; then
        log_error "設定ディレクトリが存在しません: $CONFIG_DIR"
        exit 1
    fi

    log_success "前提条件チェック完了"
}

# ドメイン設定の確認
setup_domain() {
    if [ -z "$DOMAIN" ]; then
        log_warning "CLOUDFLARE_DOMAIN 環境変数が設定されていません"
        echo ""
        log_info "以下のいずれかの方法でドメインを設定してください:"
        log_info "1. 既存ドメインを Cloudflare に追加"
        log_info "2. Cloudflare 提供の無料サブドメインを使用"
        echo ""
        read -p "ドメイン名を入力してください (例: yourdomain.com): " DOMAIN

        if [ -z "$DOMAIN" ]; then
            log_error "ドメイン名が入力されませんでした"
            exit 1
        fi
    fi

    log_info "使用ドメイン: $DOMAIN"
}

# Cloudflare 認証
authenticate_cloudflare() {
    log_info "Cloudflare 認証を開始します..."
    log_info "ブラウザで Cloudflare にログインしてください"

    if cloudflared tunnel login; then
        log_success "Cloudflare 認証が完了しました"
    else
        log_error "Cloudflare 認証に失敗しました"
        exit 1
    fi
}

# Tunnel 作成
create_tunnel() {
    log_info "Tunnel を作成しています..."

    # 既存 Tunnel の確認
    if cloudflared tunnel list | grep -q "$TUNNEL_NAME"; then
        log_warning "Tunnel '$TUNNEL_NAME' は既に存在します"

        read -p "既存の Tunnel を削除して再作成しますか？ (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "既存 Tunnel を削除しています..."
            cloudflared tunnel delete "$TUNNEL_NAME" || true
        else
            log_info "既存 Tunnel を使用します"
            return 0
        fi
    fi

    # Tunnel 作成
    if cloudflared tunnel create "$TUNNEL_NAME"; then
        log_success "Tunnel '$TUNNEL_NAME' を作成しました"
    else
        log_error "Tunnel の作成に失敗しました"
        exit 1
    fi
}

# DNS レコード設定
setup_dns_records() {
    log_info "DNS レコードを設定しています..."

    # メインアプリ用 DNS レコード
    local main_subdomain="app"
    log_info "メインアプリ用 DNS レコードを設定: $main_subdomain.$DOMAIN"

    if cloudflared tunnel route dns "$TUNNEL_NAME" "$main_subdomain.$DOMAIN"; then
        log_success "DNS レコードを設定しました: $main_subdomain.$DOMAIN"
    else
        log_warning "DNS レコードの設定に失敗しました（手動設定が必要な場合があります）"
    fi

    # API 用 DNS レコード
    local api_subdomain="api"
    log_info "API 用 DNS レコードを設定: $api_subdomain.$DOMAIN"

    if cloudflared tunnel route dns "$TUNNEL_NAME" "$api_subdomain.$DOMAIN"; then
        log_success "DNS レコードを設定しました: $api_subdomain.$DOMAIN"
    else
        log_warning "API 用 DNS レコードの設定に失敗しました"
    fi

    # カメラ用 DNS レコード
    local camera_subdomain="camera"
    log_info "カメラ用 DNS レコードを設定: $camera_subdomain.$DOMAIN"

    if cloudflared tunnel route dns "$TUNNEL_NAME" "$camera_subdomain.$DOMAIN"; then
        log_success "DNS レコードを設定しました: $camera_subdomain.$DOMAIN"
    else
        log_warning "カメラ用 DNS レコードの設定に失敗しました"
    fi
}

# 設定ファイル作成
create_config_file() {
    log_info "設定ファイルを作成しています..."

    # Tunnel ID を取得
    local tunnel_id=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')

    if [ -z "$tunnel_id" ]; then
        log_error "Tunnel ID を取得できませんでした"
        exit 1
    fi

    log_info "Tunnel ID: $tunnel_id"

    # 設定ファイル作成
    sudo tee "$CONFIG_FILE" > /dev/null <<EOF
tunnel: $tunnel_id
credentials-file: $CREDENTIALS_FILE

ingress:
  # メインアプリ (React UI)
  - hostname: app.$DOMAIN
    service: http://localhost:$UI_PORT
    originRequest:
      httpHostHeader: localhost:$UI_PORT
      noTLSVerify: true

  # API サーバー
  - hostname: api.$DOMAIN
    service: http://localhost:$API_PORT
    originRequest:
      httpHostHeader: localhost:$API_PORT
      noTLSVerify: true

  # カメラストリーム
  - hostname: camera.$DOMAIN
    service: http://localhost:$CAMERA_PORT
    originRequest:
      httpHostHeader: localhost:$CAMERA_PORT
      noTLSVerify: true

  # デフォルト（すべてのトラフィックをメインアプリに）
  - service: http://localhost:$UI_PORT
    originRequest:
      httpHostHeader: localhost:$UI_PORT
      noTLSVerify: true

# ログ設定
loglevel: info

# 接続設定
retries: 3
grace-period: 30s

# メトリクス（オプション）
metrics: localhost:2000
EOF

    # ファイル権限設定
    sudo chown cloudflared:cloudflared "$CONFIG_FILE"
    sudo chmod 600 "$CONFIG_FILE"

    log_success "設定ファイルを作成しました: $CONFIG_FILE"
}

# 認証情報ファイルのコピー
setup_credentials() {
    log_info "認証情報ファイルを設定しています..."

    # ホームディレクトリから認証情報をコピー
    local home_credentials="$HOME/.cloudflared/$TUNNEL_NAME.json"

    if [ -f "$home_credentials" ]; then
        sudo cp "$home_credentials" "$CREDENTIALS_FILE"
        sudo chown cloudflared:cloudflared "$CREDENTIALS_FILE"
        sudo chmod 600 "$CREDENTIALS_FILE"
        log_success "認証情報ファイルを設定しました"
    else
        log_error "認証情報ファイルが見つかりません: $home_credentials"
        exit 1
    fi
}

# 設定テスト
test_configuration() {
    log_info "設定をテストしています..."

    if sudo -u cloudflared cloudflared tunnel --config "$CONFIG_FILE" ingress validate; then
        log_success "設定ファイルは有効です"
    else
        log_error "設定ファイルに問題があります"
        exit 1
    fi
}

# 使用方法表示
show_usage() {
    echo ""
    log_success "Cloudflare Tunnel の設定が完了しました！"
    echo ""
    log_info "設定されたURL:"
    log_info "- メインアプリ: https://app.$DOMAIN"
    log_info "- API サーバー: https://api.$DOMAIN"
    log_info "- カメラストリーム: https://camera.$DOMAIN"
    echo ""
    log_info "次の手順:"
    log_info "1. systemd サービスを設定:"
    log_info "   sudo ./scripts/setup/setup-cloudflare-systemd.sh"
    echo ""
    log_info "2. Cloudflare Access で Google 認証を設定"
    log_info "   (詳細は docs/deployment/cloudflare-access-setup.md を参照)"
    echo ""
    log_info "3. Tunnel を手動で開始してテスト:"
    log_info "   sudo cloudflared tunnel --config $CONFIG_FILE run"
    echo ""
}

# メイン処理
main() {
    log_info "Cloudflare Tunnel 設定を開始します..."
    echo ""

    check_prerequisites
    setup_domain
    authenticate_cloudflare
    create_tunnel
    setup_dns_records
    create_config_file
    setup_credentials
    test_configuration
    show_usage

    log_success "Cloudflare Tunnel の設定が完了しました！"
}

# スクリプト実行
main "$@"
