#!/bin/bash

# 外部アクセステスト用動作確認スクリプト
# Cloudflare Tunnel + Access の動作確認

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
DOMAIN="${CLOUDFLARE_DOMAIN:-}"
TEST_TIMEOUT=10

# 使用方法表示
show_usage() {
    echo "Usage: $0 [domain]"
    echo ""
    echo "Examples:"
    echo "  $0 yourdomain.com"
    echo "  CLOUDFLARE_DOMAIN=yourdomain.com $0"
    echo ""
    echo "Environment Variables:"
    echo "  CLOUDFLARE_DOMAIN  - テスト対象のドメイン"
    echo ""
}

# ドメイン設定確認
setup_domain() {
    if [ $# -gt 0 ]; then
        DOMAIN="$1"
    fi

    if [ -z "$DOMAIN" ]; then
        log_error "ドメインが指定されていません"
        show_usage
        exit 1
    fi

    log_info "テスト対象ドメイン: $DOMAIN"
}

# DNS 解決テスト
test_dns_resolution() {
    log_info "DNS 解決テストを実行しています..."

    local subdomains=("app" "api" "camera")
    local dns_ok=true

    for subdomain in "${subdomains[@]}"; do
        local full_domain="$subdomain.$DOMAIN"
        log_info "DNS 解決テスト: $full_domain"

        if nslookup "$full_domain" >/dev/null 2>&1; then
            log_success "DNS 解決成功: $full_domain"
        else
            log_error "DNS 解決失敗: $full_domain"
            dns_ok=false
        fi
    done

    if [ "$dns_ok" = true ]; then
        log_success "すべての DNS 解決が成功しました"
        return 0
    else
        log_error "DNS 解決に失敗したドメインがあります"
        return 1
    fi
}

# HTTP 接続テスト
test_http_connectivity() {
    log_info "HTTP 接続テストを実行しています..."

    local urls=(
        "https://app.$DOMAIN"
        "https://api.$DOMAIN/health"
        "https://camera.$DOMAIN/stream"
    )

    for url in "${urls[@]}"; do
        log_info "HTTP 接続テスト: $url"

        local status_code=$(curl -s -o /dev/null -w "%{http_code}" \
                           --connect-timeout "$TEST_TIMEOUT" \
                           --max-time "$TEST_TIMEOUT" \
                           "$url" || echo "000")

        case "$status_code" in
            200)
                log_success "接続成功 (200): $url"
                ;;
            302|301)
                log_success "リダイレクト ($status_code): $url - 認証ページへの転送"
                ;;
            403)
                log_warning "アクセス拒否 (403): $url - 認証が必要"
                ;;
            000)
                log_error "接続失敗: $url - タイムアウトまたは接続エラー"
                ;;
            *)
                log_warning "予期しないレスポンス ($status_code): $url"
                ;;
        esac
    done
}

# SSL 証明書テスト
test_ssl_certificates() {
    log_info "SSL 証明書テストを実行しています..."

    local subdomains=("app" "api" "camera")

    for subdomain in "${subdomains[@]}"; do
        local full_domain="$subdomain.$DOMAIN"
        log_info "SSL 証明書テスト: $full_domain"

        if echo | openssl s_client -servername "$full_domain" \
                                   -connect "$full_domain:443" \
                                   -verify_return_error \
                                   >/dev/null 2>&1; then
            log_success "SSL 証明書有効: $full_domain"
        else
            log_error "SSL 証明書エラー: $full_domain"
        fi
    done
}

# Cloudflare 設定確認
test_cloudflare_configuration() {
    log_info "Cloudflare 設定確認を実行しています..."

    # Cloudflare IP レンジからの応答確認
    local app_url="https://app.$DOMAIN"
    log_info "Cloudflare 経由確認: $app_url"

    local cf_ray=$(curl -s -I "$app_url" | grep -i "cf-ray" | cut -d: -f2 | tr -d ' \r\n' || echo "")

    if [ -n "$cf_ray" ]; then
        log_success "Cloudflare 経由でアクセス確認 (CF-Ray: $cf_ray)"
    else
        log_warning "Cloudflare 経由でのアクセスが確認できません"
    fi

    # Access 認証確認
    local auth_response=$(curl -s -I "$app_url" | grep -i "cf-access" || echo "")

    if [ -n "$auth_response" ]; then
        log_success "Cloudflare Access が有効です"
    else
        log_warning "Cloudflare Access の設定が確認できません"
    fi
}

# ローカルサービス状態確認
test_local_services() {
    log_info "ローカルサービス状態を確認しています..."

    # デフォルトポート（環境変数で上書き可能）
    local ui_port="${UI_PORT:-3000}"
    local api_port="${API_PORT:-8000}"
    local camera_port="${CAMERA_PORT:-8001}"

    local services=(
        "UI:localhost:$ui_port"
        "API:localhost:$api_port"
        "Camera:localhost:$camera_port"
    )

    for service in "${services[@]}"; do
        local name=$(echo "$service" | cut -d: -f1)
        local host=$(echo "$service" | cut -d: -f2)
        local port=$(echo "$service" | cut -d: -f3)

        log_info "ローカルサービス確認: $name ($host:$port)"

        if nc -z "$host" "$port" 2>/dev/null; then
            log_success "サービス稼働中: $name"
        else
            log_error "サービス停止中: $name"
        fi
    done
}

# Cloudflare Tunnel サービス確認
test_tunnel_service() {
    log_info "Cloudflare Tunnel サービス状態を確認しています..."

    if systemctl is-active --quiet cloudflare-tunnel 2>/dev/null; then
        log_success "Cloudflare Tunnel サービス稼働中"

        # Tunnel 接続状態確認
        local tunnel_status=$(systemctl status cloudflare-tunnel --no-pager -l 2>/dev/null | grep "Registered tunnel connection" | tail -1 || echo "")

        if [ -n "$tunnel_status" ]; then
            log_success "Tunnel 接続確立済"
        else
            log_warning "Tunnel 接続状態が不明です"
        fi

    elif [ -f /etc/systemd/system/cloudflare-tunnel.service ]; then
        log_error "Cloudflare Tunnel サービスが停止中です"
        log_info "サービス開始: sudo systemctl start cloudflare-tunnel"
    else
        log_warning "Cloudflare Tunnel サービスが設定されていません"
    fi
}

# 詳細テスト結果レポート
generate_test_report() {
    echo ""
    log_info "=========================================="
    log_info "        テスト結果サマリー"
    log_info "=========================================="
    echo ""

    log_info "テスト実行時刻: $(date)"
    log_info "対象ドメイン: $DOMAIN"
    echo ""

    log_info "推奨される次のステップ:"
    echo ""
    log_info "1. DNS とHTTP接続が成功している場合:"
    log_info "   → Cloudflare Access で認証設定を完了"
    log_info "   → 外部ネットワークからブラウザでアクセステスト"
    echo ""
    log_info "2. 接続に問題がある場合:"
    log_info "   → ローカルサービスの起動確認: ./scripts/start-development.sh"
    log_info "   → Tunnel サービスの確認: sudo systemctl status cloudflare-tunnel"
    log_info "   → Cloudflare 設定の確認: cloudflared tunnel list"
    echo ""
    log_info "3. 詳細ログ確認:"
    log_info "   → sudo journalctl -u cloudflare-tunnel -f"
    echo ""
}

# エラーハンドリング
handle_error() {
    log_error "テスト実行中にエラーが発生しました"
    log_info "詳細なデバッグ情報が必要な場合は、-v オプションでverboseモードを使用してください"
    exit 1
}

# メイン処理
main() {
    log_info "Cloudflare Tunnel 外部アクセステストを開始します..."
    echo ""

    # エラーハンドリング設定
    trap handle_error ERR

    # ドメイン設定
    setup_domain "$@"
    echo ""

    # 各テスト実行
    test_dns_resolution
    echo ""

    test_ssl_certificates
    echo ""

    test_http_connectivity
    echo ""

    test_cloudflare_configuration
    echo ""

    test_local_services
    echo ""

    test_tunnel_service
    echo ""

    # テスト結果レポート
    generate_test_report

    log_success "外部アクセステストが完了しました！"
}

# 引数チェック
if [ $# -eq 0 ] && [ -z "$DOMAIN" ]; then
    show_usage
    exit 1
fi

# スクリプト実行
main "$@"
