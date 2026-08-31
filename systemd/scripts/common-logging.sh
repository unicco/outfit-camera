#!/bin/bash

# 共通ログ関数
# systemd スクリプト間で統一されたログ出力を提供

# カラー定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# ログレベル
LOG_LEVEL_INFO="INFO"
LOG_LEVEL_WARN="WARN"
LOG_LEVEL_ERROR="ERROR"
LOG_LEVEL_DEBUG="DEBUG"

# ログ関数
log() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        "$LOG_LEVEL_INFO")
            echo -e "${GREEN}[INFO]${NC} $timestamp - $message"
            ;;
        "$LOG_LEVEL_WARN")
            echo -e "${YELLOW}[WARN]${NC} $timestamp - $message"
            ;;
        "$LOG_LEVEL_ERROR")
            echo -e "${RED}[ERROR]${NC} $timestamp - $message"
            ;;
        "$LOG_LEVEL_DEBUG")
            echo -e "${BLUE}[DEBUG]${NC} $timestamp - $message"
            ;;
        *)
            echo -e "$timestamp - $message"
            ;;
    esac
}

# 便利なラッパー関数
log_info() {
    log "$LOG_LEVEL_INFO" "$1"
}

log_warn() {
    log "$LOG_LEVEL_WARN" "$1"
}

log_error() {
    log "$LOG_LEVEL_ERROR" "$1"
}

log_debug() {
    log "$LOG_LEVEL_DEBUG" "$1"
}

# systemd-cat へのログ出力（オプション）
log_to_journal() {
    local level=$1
    local message=$2
    local identifier=${3:-"coordinate-recorder"}

    case $level in
        "$LOG_LEVEL_INFO")
            echo "$message" | systemd-cat -t "$identifier" -p info
            ;;
        "$LOG_LEVEL_WARN")
            echo "$message" | systemd-cat -t "$identifier" -p warning
            ;;
        "$LOG_LEVEL_ERROR")
            echo "$message" | systemd-cat -t "$identifier" -p err
            ;;
        "$LOG_LEVEL_DEBUG")
            echo "$message" | systemd-cat -t "$identifier" -p debug
            ;;
    esac
}
