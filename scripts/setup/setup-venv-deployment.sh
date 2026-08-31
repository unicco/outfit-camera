#!/bin/bash
set -e

# 仮想環境セットアップ & デプロイメント支援スクリプト
# Raspberry Pi での externally-managed-environment エラーを解決し、
# 仮想環境の作成・管理と依存関係のインストールを自動化

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs/deploy"
LOG_FILE="${LOG_DIR}/deploy-production-$(date +%Y%m%d-%H%M%S).log"
VENV_DIR="${PROJECT_ROOT}/venv"

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# エラーハンドリング
handle_error() {
    local exit_code=$?
    log_error "エラーが発生しました (終了コード: ${exit_code})"
    log_error "ログファイル: ${LOG_FILE}"
    exit ${exit_code}
}

trap handle_error ERR

# 使用方法
usage() {
    cat << EOF
使用方法: $0 [オプション]

仮想環境セットアップ & デプロイメント支援スクリプト
Raspberry Pi での externally-managed-environment エラーを解決

オプション:
    -h, --help              このヘルプを表示
    -f, --force             確認なしで実行
    -s, --skip-backup       バックアップをスキップ
    -r, --restart-only      サービスの再起動のみ実行
    -c, --check-only        ヘルスチェックのみ実行
    -u, --update-deps       依存関係の更新のみ実行
    -v, --verbose           詳細なログを表示

例:
    $0                      # 通常のデプロイ
    $0 --force             # 確認なしで実行
    $0 --restart-only      # サービスの再起動のみ
    $0 --check-only        # ヘルスチェックのみ

EOF
    exit 0
}

# オプション解析
FORCE=false
SKIP_BACKUP=false
RESTART_ONLY=false
CHECK_ONLY=false
UPDATE_DEPS_ONLY=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -s|--skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        -r|--restart-only)
            RESTART_ONLY=true
            shift
            ;;
        -c|--check-only)
            CHECK_ONLY=true
            shift
            ;;
        -u|--update-deps)
            UPDATE_DEPS_ONLY=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        *)
            log_error "不明なオプション: $1"
            usage
            ;;
    esac
done

# 確認プロンプト
confirm_deployment() {
    if [ "${FORCE}" = false ] && [ "${CHECK_ONLY}" = false ]; then
        echo -e "${YELLOW}本番環境へのデプロイを実行します。続行しますか？${NC}"
        read -p "続行する場合は 'yes' と入力してください: " response
        if [ "$response" != "yes" ]; then
            log_info "デプロイをキャンセルしました"
            exit 0
        fi
    fi
}

# 環境チェック
check_environment() {
    log_info "環境チェックを開始します..."

    # Raspberry Pi チェック
    if [ -f /proc/device-tree/model ]; then
        MODEL=$(cat /proc/device-tree/model | tr -d '\0')
        log_info "デバイス: ${MODEL}"
        if [[ ! "$MODEL" =~ "Raspberry Pi" ]]; then
            log_warning "Raspberry Pi ではない環境で実行されています"
        fi
    fi

    # Python バージョンチェック
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    log_info "Python バージョン: ${PYTHON_VERSION}"

    # ディスク容量チェック
    DISK_USAGE=$(df -h "${PROJECT_ROOT}" | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ ${DISK_USAGE} -gt 90 ]; then
        log_warning "ディスク使用率が高いです: ${DISK_USAGE}%"
    fi
}

# バックアップ作成
create_backup() {
    if [ "${SKIP_BACKUP}" = false ] && [ "${CHECK_ONLY}" = false ] && [ "${RESTART_ONLY}" = false ]; then
        log_info "バックアップを作成します..."

        BACKUP_DIR="${PROJECT_ROOT}/backups/deploy-$(date +%Y%m%d-%H%M%S)"
        mkdir -p "${BACKUP_DIR}"

        # 仮想環境のパッケージリストを保存
        if [ -d "${VENV_DIR}" ]; then
            log_info "インストール済パッケージリストを保存..."
            source "${VENV_DIR}/bin/activate"
            pip freeze > "${BACKUP_DIR}/pip-freeze.txt"
            deactivate
        fi

        # 設定ファイルのバックアップ
        if [ -f "${PROJECT_ROOT}/.env" ]; then
            cp "${PROJECT_ROOT}/.env" "${BACKUP_DIR}/"
        fi

        log_success "バックアップ完了: ${BACKUP_DIR}"
    fi
}

# 仮想環境管理
manage_venv() {
    log_info "仮想環境を管理します..."

    # 仮想環境の作成または確認
    if [ ! -d "${VENV_DIR}" ]; then
        log_info "仮想環境を作成します..."
        python3 -m venv "${VENV_DIR}"
        log_success "仮想環境を作成しました: ${VENV_DIR}"
    else
        log_info "既存の仮想環境を使用します: ${VENV_DIR}"
    fi

    # 仮想環境のアクティベート
    log_info "仮想環境をアクティベートします..."
    source "${VENV_DIR}/bin/activate"

    # pip のアップグレード
    log_info "pip をアップグレードします..."
    pip install --upgrade pip

    log_success "仮想環境の準備完了"
}

install_requirements_if_present() {
    local label="$1"
    local path="$2"

    if [ -f "$path" ]; then
        log_info "${label} をインストール..."
        pip install -r "$path"
        return 0
    fi

    return 1
}

# 依存関係のインストール
install_dependencies() {
    log_info "依存関係をインストールします..."

    # API 依存関係
    local -a api_requirements_candidates=()

    if [ -f "${PROJECT_ROOT}/api/v2/requirements.txt" ]; then
        api_requirements_candidates+=("${PROJECT_ROOT}/api/v2/requirements.txt|API 依存関係 (api/v2/requirements.txt)")
    fi

    if [ -f "${PROJECT_ROOT}/requirements-api.txt" ]; then
        api_requirements_candidates+=("${PROJECT_ROOT}/requirements-api.txt|API 依存関係 (requirements-api.txt)")
    fi

    if [ -f "${PROJECT_ROOT}/api/requirements.txt" ]; then
        api_requirements_candidates+=("${PROJECT_ROOT}/api/requirements.txt|API 依存関係 (api/requirements.txt)")
    fi

    local installed_api_requirements=false
    for candidate in "${api_requirements_candidates[@]}"; do
        local path="${candidate%%|*}"
        local label="${candidate##*|}"
        if install_requirements_if_present "$label" "$path"; then
            installed_api_requirements=true
            break
        fi
    done

    if [ "$installed_api_requirements" = false ]; then
        log_warning "API 依存関係ファイルが見つかりません"
    fi

    # Camera 依存関係
    install_requirements_if_present "Camera 依存関係" "${PROJECT_ROOT}/camera/requirements.txt"

    # 共通依存関係
    if ! install_requirements_if_present "共通依存関係" "${PROJECT_ROOT}/requirements.txt"; then
        log_info "共通依存関係ファイル (requirements.txt) は見つかりませんでした"
    fi

    # Google Photos API パッケージチェック
    if ! pip show google-api-python-client > /dev/null 2>&1; then
        log_info "Google Photos API パッケージをインストール..."
        pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
    fi

    log_success "依存関係のインストール完了"
}

# systemd サービス更新
update_systemd_services() {
    log_info "systemd サービスを更新します..."

    # サービス更新スクリプトを実行
    if [ -x "${SCRIPT_DIR}/update-systemd-services.sh" ]; then
        "${SCRIPT_DIR}/update-systemd-services.sh"
    else
        log_warning "systemd 更新スクリプトが見つかりません"

        # 基本的なサービス設定更新
        if [ -d "/etc/systemd/system" ]; then
            # coordinate-api.service の仮想環境パス更新
            if [ -f "/etc/systemd/system/coordinate-api.service" ]; then
                log_info "coordinate-api.service を更新..."
                sudo sed -i "s|ExecStart=.*|ExecStart=${VENV_DIR}/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000|" \
                    /etc/systemd/system/coordinate-api.service
            fi

            # coordinate-camera.service の仮想環境パス更新
            if [ -f "/etc/systemd/system/coordinate-camera.service" ]; then
                log_info "coordinate-camera.service を更新..."
                sudo sed -i "s|ExecStart=.*|ExecStart=${VENV_DIR}/bin/python -m uvicorn camera.main:app --host 0.0.0.0 --port 8001|" \
                    /etc/systemd/system/coordinate-camera.service
            fi
        fi
    fi

    # systemd 設定をリロード
    sudo systemctl daemon-reload
    log_success "systemd サービスの更新完了"
}

# サービス再起動
restart_services() {
    log_info "サービスを再起動します..."

    # API サービス
    if systemctl is-enabled coordinate-api.service > /dev/null 2>&1; then
        log_info "coordinate-api.service を再起動..."
        sudo systemctl restart coordinate-api.service
        sleep 5
    fi

    # Camera サービス
    if systemctl is-enabled coordinate-camera.service > /dev/null 2>&1; then
        log_info "coordinate-camera.service を再起動..."
        sudo systemctl restart coordinate-camera.service
        sleep 5
    fi

    log_success "サービスの再起動完了"
}

# ヘルスチェック
run_health_check() {
    log_info "ヘルスチェックを実行します..."

    # ヘルスチェックスクリプトを実行
    if [ -x "${SCRIPT_DIR}/../health-check.sh" ]; then
        "${SCRIPT_DIR}/../health-check.sh"
    else
        log_warning "ヘルスチェックスクリプトが見つかりません。基本チェックを実行します..."

        # API ヘルスチェック
        if command -v curl > /dev/null 2>&1; then
            if curl -f -s http://localhost:8000/health > /dev/null; then
                log_success "API サーバー: 正常"
            else
                log_error "API サーバー: 応答なし"
            fi

            # Camera ヘルスチェック
            if curl -f -s http://localhost:8001/health > /dev/null; then
                log_success "Camera サーバー: 正常"
            else
                log_error "Camera サーバー: 応答なし"
            fi
        else
            log_info "Python httpx でヘルスチェックを実行..."
            python3 -c "
import httpx
import sys

try:
    # API チェック
    response = httpx.get('http://localhost:8000/health', timeout=5)
    if response.status_code == 200:
        print('${GREEN}[SUCCESS]${NC} API サーバー: 正常')
    else:
        print('${RED}[ERROR]${NC} API サーバー: ステータス', response.status_code)
        sys.exit(1)

    # Camera チェック
    response = httpx.get('http://localhost:8001/health', timeout=5)
    if response.status_code == 200:
        print('${GREEN}[SUCCESS]${NC} Camera サーバー: 正常')
    else:
        print('${RED}[ERROR]${NC} Camera サーバー: ステータス', response.status_code)
        sys.exit(1)

except Exception as e:
    print('${RED}[ERROR]${NC} ヘルスチェックエラー:', e)
    sys.exit(1)
"
        fi
    fi
}

# デプロイ完了通知
notify_completion() {
    local status=$1
    local message=$2

    if [ "$status" = "success" ]; then
        log_success "========================================"
        log_success "デプロイが正常に完了しました！"
        log_success "========================================"
    else
        log_error "========================================"
        log_error "デプロイ中にエラーが発生しました"
        log_error "$message"
        log_error "========================================"
    fi

    log_info "ログファイル: ${LOG_FILE}"
}

# メイン処理
main() {
    log_info "========================================"
    log_info "本番環境デプロイを開始します"
    log_info "========================================"

    # チェックのみモード
    if [ "${CHECK_ONLY}" = true ]; then
        check_environment
        run_health_check
        exit 0
    fi

    # 再起動のみモード
    if [ "${RESTART_ONLY}" = true ]; then
        restart_services
        run_health_check
        exit 0
    fi

    # 依存関係更新のみモード
    if [ "${UPDATE_DEPS_ONLY}" = true ]; then
        check_environment
        manage_venv
        install_dependencies
        exit 0
    fi

    # 通常デプロイフロー
    confirm_deployment
    check_environment
    create_backup

    # 仮想環境管理と依存関係インストール
    manage_venv
    install_dependencies

    # systemd サービス更新と再起動
    update_systemd_services
    restart_services

    # ヘルスチェック
    run_health_check

    # 完了通知
    notify_completion "success" ""

    # 仮想環境を非アクティブ化
    deactivate
}

# スクリプト実行
main "$@"
