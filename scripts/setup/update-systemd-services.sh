#!/bin/bash
set -e

# systemd サービス更新スクリプト
# 仮想環境パスを自動的に更新し、サービス設定を最適化

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/venv"
SYSTEMD_DIR="/etc/systemd/system"

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ログ出力関数
log_error() {
    echo -e "${RED}[ERROR]${NC} $@"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $@"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $@"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $@"
}

# 使用方法
usage() {
    cat << EOF
使用方法: $0 [オプション]

systemd サービス更新スクリプト - 仮想環境パスを自動更新

オプション:
    -h, --help              このヘルプを表示
    -f, --force             確認なしで実行
    -d, --dry-run           実際の変更を行わずに実行
    -v, --verbose           詳細なログを表示

EOF
    exit 0
}

# オプション解析
FORCE=false
DRY_RUN=false
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
        -d|--dry-run)
            DRY_RUN=true
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

# 環境チェック
check_environment() {
    log_info "環境をチェックしています..."

    # 仮想環境の存在確認
    if [ ! -d "${VENV_DIR}" ]; then
        log_error "仮想環境が見つかりません: ${VENV_DIR}"
        log_info "先に setup-venv-deployment.sh を実行してください"
        exit 1
    fi

    # Python 実行ファイルの確認
    if [ ! -f "${VENV_DIR}/bin/python" ]; then
        log_error "Python 実行ファイルが見つかりません: ${VENV_DIR}/bin/python"
        exit 1
    fi

    # systemd ディレクトリの確認
    if [ ! -d "${SYSTEMD_DIR}" ]; then
        log_error "systemd ディレクトリが見つかりません: ${SYSTEMD_DIR}"
        exit 1
    fi

    log_success "環境チェック完了"
}

# サービステンプレート作成
create_service_template() {
    local service_name=$1
    local description=$2
    local exec_command=$3
    local working_directory=$4
    local environment_file="${PROJECT_ROOT}/.env"

    cat << EOF
[Unit]
Description=${description}
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=exec
User=pi
Group=pi
WorkingDirectory=${working_directory}
Environment="PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONPATH=${PROJECT_ROOT}"
EnvironmentFile=-${environment_file}
ExecStart=${exec_command}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${service_name}

# プロセス管理
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

# リソース制限
MemoryLimit=512M
CPUQuota=100%

# セキュリティ設定
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
}

# API サービス更新
update_api_service() {
    local service_name="coordinate-api.service"
    local service_file="${SYSTEMD_DIR}/${service_name}"

    log_info "API サービスを更新しています: ${service_name}"

    # サービステンプレート作成
    local exec_command="${VENV_DIR}/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload-exclude 'photos/*' --reload-exclude 'logs/*'"
    local service_content=$(create_service_template \
        "coordinate-api" \
        "Coordinate Recorder API Service" \
        "${exec_command}" \
        "${PROJECT_ROOT}")

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] 以下の内容でサービスファイルを作成します:"
        echo "${service_content}"
    else
        # 既存のサービスファイルのバックアップ
        if [ -f "${service_file}" ]; then
            sudo cp "${service_file}" "${service_file}.bak"
            log_info "既存のサービスファイルをバックアップしました: ${service_file}.bak"
        fi

        # 新しいサービスファイルの作成
        echo "${service_content}" | sudo tee "${service_file}" > /dev/null
        log_success "API サービスファイルを更新しました: ${service_file}"
    fi
}

# Camera サービス更新
update_camera_service() {
    local service_name="coordinate-camera.service"
    local service_file="${SYSTEMD_DIR}/${service_name}"

    log_info "Camera サービスを更新しています: ${service_name}"

    # サービステンプレート作成
    local exec_command="${VENV_DIR}/bin/python -m uvicorn camera.main:app --host 0.0.0.0 --port 8001"
    local service_content=$(create_service_template \
        "coordinate-camera" \
        "Coordinate Recorder Camera Service" \
        "${exec_command}" \
        "${PROJECT_ROOT}/camera")

    # Camera 特有の設定を追加
    service_content=$(echo "${service_content}" | sed '/^\[Service\]/a\
# Camera specific settings\
Environment="LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libatomic.so.1"\
SupplementaryGroups=video')

    if [ "${DRY_RUN}" = true ]; then
        log_info "[DRY RUN] 以下の内容でサービスファイルを作成します:"
        echo "${service_content}"
    else
        # 既存のサービスファイルのバックアップ
        if [ -f "${service_file}" ]; then
            sudo cp "${service_file}" "${service_file}.bak"
            log_info "既存のサービスファイルをバックアップしました: ${service_file}.bak"
        fi

        # 新しいサービスファイルの作成
        echo "${service_content}" | sudo tee "${service_file}" > /dev/null
        log_success "Camera サービスファイルを更新しました: ${service_file}"
    fi
}

# サービス権限設定
set_service_permissions() {
    if [ "${DRY_RUN}" = false ]; then
        log_info "サービスファイルの権限を設定しています..."

        sudo chmod 644 "${SYSTEMD_DIR}/coordinate-api.service" 2>/dev/null || true
        sudo chmod 644 "${SYSTEMD_DIR}/coordinate-camera.service" 2>/dev/null || true

        log_success "権限設定完了"
    fi
}

# systemd 設定リロード
reload_systemd() {
    if [ "${DRY_RUN}" = false ]; then
        log_info "systemd 設定をリロードしています..."
        sudo systemctl daemon-reload
        log_success "systemd リロード完了"
    else
        log_info "[DRY RUN] systemd daemon-reload をスキップします"
    fi
}

# サービス有効化
enable_services() {
    if [ "${DRY_RUN}" = false ]; then
        log_info "サービスを有効化しています..."

        # API サービス
        if [ -f "${SYSTEMD_DIR}/coordinate-api.service" ]; then
            sudo systemctl enable coordinate-api.service
            log_success "coordinate-api.service を有効化しました"
        fi

        # Camera サービス
        if [ -f "${SYSTEMD_DIR}/coordinate-camera.service" ]; then
            sudo systemctl enable coordinate-camera.service
            log_success "coordinate-camera.service を有効化しました"
        fi
    else
        log_info "[DRY RUN] サービスの有効化をスキップします"
    fi
}

# サービス状態確認
check_service_status() {
    log_info "サービス状態を確認しています..."

    # API サービス
    if systemctl is-active --quiet coordinate-api.service; then
        log_success "coordinate-api.service: 実行中"
    else
        log_warning "coordinate-api.service: 停止中"
    fi

    # Camera サービス
    if systemctl is-active --quiet coordinate-camera.service; then
        log_success "coordinate-camera.service: 実行中"
    else
        log_warning "coordinate-camera.service: 停止中"
    fi
}

# メイン処理
main() {
    log_info "========================================"
    log_info "systemd サービス更新を開始します"
    log_info "========================================"

    # 環境チェック
    check_environment

    # 各サービスの更新
    update_api_service
    update_camera_service

    # 権限設定
    set_service_permissions

    # systemd リロード
    reload_systemd

    # サービス有効化
    enable_services

    # 状態確認
    check_service_status

    log_success "========================================"
    log_success "systemd サービス更新が完了しました"
    log_success "========================================"

    if [ "${DRY_RUN}" = true ]; then
        log_warning "これはドライラン実行でした。実際の変更は行われていません。"
    else
        log_info "サービスを再起動するには以下のコマンドを実行してください:"
        log_info "  sudo systemctl restart coordinate-api.service"
        log_info "  sudo systemctl restart coordinate-camera.service"
    fi
}

# スクリプト実行
main "$@"
