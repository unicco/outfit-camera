#!/bin/bash
set -e

# ヘルスチェックスクリプト
# API、Camera、UI サービスの動作確認を実行

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs/health-check"
LOG_FILE="${LOG_DIR}/health-check-$(date +%Y%m%d-%H%M%S).log"

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# デフォルト設定
API_PORT="${API_PORT:-8000}"
CAMERA_PORT="${CAMERA_PORT:-8001}"
UI_PORT="${UI_PORT:-5173}"
TIMEOUT=10
RETRY_COUNT=3
RETRY_DELAY=2

# ログディレクトリ作成
mkdir -p "${LOG_DIR}"

# ログ出力関数
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $@" | tee -a "${LOG_FILE}"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $@" | tee -a "${LOG_FILE}"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $@" | tee -a "${LOG_FILE}"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $@" | tee -a "${LOG_FILE}"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $@" | tee -a "${LOG_FILE}"
}

# 使用方法
usage() {
    cat << EOF
使用方法: $0 [オプション]

ヘルスチェックスクリプト - 各サービスの動作確認

オプション:
    -h, --help              このヘルプを表示
    -v, --verbose           詳細なログを表示
    -q, --quiet             エラー以外のログを抑制
    -t, --timeout SECONDS   タイムアウト時間（デフォルト: 10秒）
    -r, --retries COUNT     リトライ回数（デフォルト: 3回）
    --api-only              API サーバーのみチェック
    --camera-only           Camera サーバーのみチェック
    --ui-only               UI サーバーのみチェック

例:
    $0                      # すべてのサービスをチェック
    $0 --api-only          # API サーバーのみチェック
    $0 -t 30 -r 5          # タイムアウト30秒、リトライ5回

EOF
    exit 0
}

# オプション解析
VERBOSE=false
QUIET=false
CHECK_API=true
CHECK_CAMERA=true
CHECK_UI=true

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -r|--retries)
            RETRY_COUNT="$2"
            shift 2
            ;;
        --api-only)
            CHECK_CAMERA=false
            CHECK_UI=false
            shift
            ;;
        --camera-only)
            CHECK_API=false
            CHECK_UI=false
            shift
            ;;
        --ui-only)
            CHECK_API=false
            CHECK_CAMERA=false
            shift
            ;;
        *)
            log_error "不明なオプション: $1"
            usage
            ;;
    esac
done

# 結果格納用
HEALTH_STATUS=0
HEALTH_RESULTS=()

# httpx でヘルスチェック実行
check_with_httpx() {
    local url=$1
    local service_name=$2
    local retry_count=$3

    python3 << EOF
import httpx
import sys
import time

url = "$url"
service_name = "$service_name"
timeout = $TIMEOUT
retry_count = $retry_count
retry_delay = $RETRY_DELAY

for attempt in range(retry_count):
    try:
        if attempt > 0:
            print(f"[INFO] リトライ {attempt}/{retry_count-1}...")
            time.sleep(retry_delay)

        response = httpx.get(url, timeout=timeout, follow_redirects=True)

        if response.status_code == 200:
            print(f"[SUCCESS] {service_name}: 正常 (ステータス: {response.status_code})")

            # レスポンスボディの確認
            if 'application/json' in response.headers.get('content-type', ''):
                data = response.json()
                if 'status' in data:
                    print(f"[INFO] ステータス: {data['status']}")
                if 'version' in data:
                    print(f"[INFO] バージョン: {data['version']}")
            sys.exit(0)
        else:
            print(f"[WARNING] {service_name}: ステータスコード {response.status_code}")

    except httpx.TimeoutException:
        print(f"[WARNING] {service_name}: タイムアウト ({timeout}秒)")
    except httpx.ConnectError:
        print(f"[WARNING] {service_name}: 接続エラー")
    except Exception as e:
        print(f"[WARNING] {service_name}: エラー - {e}")

print(f"[ERROR] {service_name}: {retry_count}回のリトライ後も応答なし")
sys.exit(1)
EOF

    return $?
}

# API サーバーチェック
check_api_server() {
    if [ "$CHECK_API" != true ]; then
        return 0
    fi

    log_info "API サーバーをチェックしています..."

    local api_url="http://localhost:${API_PORT}/health"

    if check_with_httpx "$api_url" "API サーバー" "$RETRY_COUNT"; then
        HEALTH_RESULTS+=("API: OK")

        # 詳細なエンドポイントチェック（verbose モード時）
        if [ "$VERBOSE" = true ]; then
            log_info "追加エンドポイントをチェック..."

            # docs エンドポイント
            if check_with_httpx "http://localhost:${API_PORT}/docs" "API Docs" 1; then
                log_success "API ドキュメント: アクセス可能"
            fi

            # photos エンドポイント
            if check_with_httpx "http://localhost:${API_PORT}/api/v2/v1/photos" "Photos API" 1; then
                log_success "Photos API: アクセス可能"
            fi
        fi
    else
        HEALTH_RESULTS+=("API: FAILED")
        HEALTH_STATUS=1
        return 1
    fi
}

# Camera サーバーチェック
check_camera_server() {
    if [ "$CHECK_CAMERA" != true ]; then
        return 0
    fi

    log_info "Camera サーバーをチェックしています..."

    local camera_url="http://localhost:${CAMERA_PORT}/health"

    if check_with_httpx "$camera_url" "Camera サーバー" "$RETRY_COUNT"; then
        HEALTH_RESULTS+=("Camera: OK")

        # カメラ状態チェック（verbose モード時）
        if [ "$VERBOSE" = true ]; then
            log_info "カメラ状態を確認..."

            if check_with_httpx "http://localhost:${CAMERA_PORT}/status" "Camera Status" 1; then
                log_success "カメラステータス: アクセス可能"
            fi
        fi
    else
        HEALTH_RESULTS+=("Camera: FAILED")
        HEALTH_STATUS=1
        return 1
    fi
}

# UI サーバーチェック
check_ui_server() {
    if [ "$CHECK_UI" != true ]; then
        return 0
    fi

    log_info "UI サーバーをチェックしています..."

    # UI サーバーは開発環境でのみ実行されることが多い
    local ui_url="http://localhost:${UI_PORT}"

    # UI サーバーのチェックは失敗しても全体のステータスには影響しない
    if check_with_httpx "$ui_url" "UI サーバー" 1; then
        HEALTH_RESULTS+=("UI: OK")
    else
        HEALTH_RESULTS+=("UI: NOT RUNNING")
        log_warning "UI サーバーは起動していません（開発環境でのみ必要）"
    fi
}

# システム情報取得
check_system_info() {
    if [ "$VERBOSE" = true ]; then
        log_info "========================================"
        log_info "システム情報"
        log_info "========================================"

        # メモリ使用状況
        if command -v free > /dev/null 2>&1; then
            log_info "メモリ使用状況:"
            free -h | grep -E "^(Mem|Swap):" | while read line; do
                log_info "  $line"
            done
        fi

        # ディスク使用状況
        log_info "ディスク使用状況:"
        df -h "${PROJECT_ROOT}" | tail -n 1 | while read filesystem size used avail use mounted; do
            log_info "  使用率: $use (使用: $used / 全体: $size)"
        done

        # プロセス状態
        log_info "関連プロセス:"
        ps aux | grep -E "(uvicorn|coordinate)" | grep -v grep | while read line; do
            log_info "  $line"
        done || log_info "  実行中のプロセスなし"
    fi
}

# データベース接続チェック
check_database() {
    if [ "$VERBOSE" = true ] && [ "$CHECK_API" = true ]; then
        log_info "データベース接続をチェックしています..."

        # .env ファイルから DATABASE_URL を読み込む
        if [ -f "${PROJECT_ROOT}/.env" ]; then
            source "${PROJECT_ROOT}/.env"

            if [ -n "$DATABASE_URL" ]; then
                # PostgreSQL の場合
                if [[ "$DATABASE_URL" =~ postgresql:// ]]; then
                    # DATABASE_URL から接続情報を抽出
                    if command -v psql > /dev/null 2>&1; then
                        if psql "$DATABASE_URL" -c "SELECT 1;" > /dev/null 2>&1; then
                            log_success "データベース: 接続可能"
                        else
                            log_warning "データベース: 接続不可"
                        fi
                    else
                        log_info "psql コマンドが見つかりません"
                    fi
                fi
            fi
        fi
    fi
}

# 結果サマリー表示
display_summary() {
    echo
    log_info "========================================"
    log_info "ヘルスチェック結果サマリー"
    log_info "========================================"

    for result in "${HEALTH_RESULTS[@]}"; do
        if [[ "$result" =~ "OK" ]]; then
            log_success "$result"
        elif [[ "$result" =~ "NOT RUNNING" ]]; then
            log_warning "$result"
        else
            log_error "$result"
        fi
    done

    echo
    if [ $HEALTH_STATUS -eq 0 ]; then
        log_success "すべての必須サービスが正常に動作しています"
    else
        log_error "一部のサービスに問題があります"
        log_info "詳細はログファイルを確認してください: $LOG_FILE"
    fi
}

# メイン処理
main() {
    if [ "$QUIET" != true ]; then
        log_info "========================================"
        log_info "ヘルスチェックを開始します"
        log_info "========================================"
        log_info "タイムアウト: ${TIMEOUT}秒"
        log_info "リトライ回数: ${RETRY_COUNT}回"
        echo
    fi

    # 各サービスのチェック
    check_api_server
    check_camera_server
    check_ui_server

    # システム情報
    check_system_info

    # データベースチェック
    check_database

    # サマリー表示
    if [ "$QUIET" != true ]; then
        display_summary
    fi

    exit $HEALTH_STATUS
}

# スクリプト実行
main "$@"
