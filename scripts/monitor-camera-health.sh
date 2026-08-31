#!/bin/bash

# Camera サービス ヘルスモニター
# systemd サービス内で動作する内蔵監視機能
# Kiosk サービスのパターンを参考にした実装

set -euo pipefail

# 設定
CAMERA_URL="${CAMERA_URL:-http://localhost:8001}"
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-1800}"  # 30分毎
TIMEOUT="${TIMEOUT:-5}"  # 5秒タイムアウト
MAX_CONSECUTIVE_FAILURES="${MAX_CONSECUTIVE_FAILURES:-3}"  # 3回連続失敗で終了

# カウンター
consecutive_failures=0

log_info() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1"
}

log_warning() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARNING] $1"
}

log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1"
}

# HTTP health endpoint チェック
check_http_health() {
    local response
    local curl_exit_code

    if ! command -v curl >/dev/null 2>&1; then
        log_error "curl command is not available for health check"
        return 1
    fi

    response=$(curl -s --max-time "$TIMEOUT" "$CAMERA_URL/health" 2>/dev/null)
    curl_exit_code=$?

    if [ $curl_exit_code -eq 0 ]; then
        if echo "$response" | grep -q '"status":"healthy"'; then
            return 0
        else
            log_warning "Health endpoint returned non-healthy status: $response"
            return 1
        fi
    else
        log_warning "Health endpoint request failed (curl exit code: $curl_exit_code)"
        return 1
    fi
}

# PIR センサー基本応答確認（簡素化）
check_pir_sensor() {
    local response
    local curl_exit_code

    if ! command -v curl >/dev/null 2>&1; then
        log_error "curl command is not available for PIR sensor check"
        return 1
    fi

    response=$(curl -s --max-time "$TIMEOUT" "$CAMERA_URL/pir/status" 2>/dev/null)
    curl_exit_code=$?

    if [ $curl_exit_code -eq 0 ]; then
        # PIR エンドポイントが応答すれば OK（詳細な監視は monitor-pir-health.sh が担当）
        if echo "$response" | grep -q '"enabled":'; then
            return 0
        else
            log_warning "PIR status endpoint returned invalid response: $response"
            return 1
        fi
    else
        log_warning "PIR status endpoint request failed (curl exit code: $curl_exit_code)"
        return 1
    fi
}

# カメラデバイス可用性チェック
check_camera_device() {
    # /dev/video* デバイスの存在確認
    if ! ls /dev/video* >/dev/null 2>&1; then
        log_warning "No camera devices found in /dev/video*"
        return 1
    fi

    # camera_service.py プロセスがカメラデバイスを使用中か確認
    if ! command -v pgrep >/dev/null 2>&1; then
        log_error "pgrep command is not available for process checking"
        return 1
    fi

    if ! pgrep -f camera_service.py >/dev/null; then
        log_warning "camera_service.py process not found"
        return 1
    fi

    return 0
}

# ポート 8001 待機状態チェック
check_port_listening() {
    # netstat を試行
    if command -v netstat >/dev/null 2>&1; then
        if netstat -tuln 2>/dev/null | grep -q ":8001 "; then
            return 0
        fi
    fi

    # netstat が失敗した場合は ss を試行
    if command -v ss >/dev/null 2>&1; then
        if ss -tuln 2>/dev/null | grep -q ":8001 "; then
            return 0
        fi
    fi

    # 両方とも失敗した場合
    if ! command -v netstat >/dev/null 2>&1 && ! command -v ss >/dev/null 2>&1; then
        log_error "Neither netstat nor ss command is available for port checking"
    else
        log_warning "Port 8001 is not listening (checked with available tools)"
    fi
    return 1
}

# 総合ヘルスチェック
perform_health_check() {
    local checks_passed=0
    local total_checks=4

    log_info "Starting health check cycle..."

    # 1. HTTP health endpoint
    if check_http_health; then
        log_info "✅ HTTP health endpoint: OK"
        ((checks_passed++))
    else
        log_error "❌ HTTP health endpoint: FAILED"
    fi

    # 2. PIR センサー応答
    if check_pir_sensor; then
        log_info "✅ PIR sensor response: OK"
        ((checks_passed++))
    else
        log_error "❌ PIR sensor response: FAILED"
    fi

    # 3. カメラデバイス可用性
    if check_camera_device; then
        log_info "✅ Camera device availability: OK"
        ((checks_passed++))
    else
        log_error "❌ Camera device availability: FAILED"
    fi

    # 4. ポート待機状態
    if check_port_listening; then
        log_info "✅ Port 8001 listening: OK"
        ((checks_passed++))
    else
        log_error "❌ Port 8001 listening: FAILED"
    fi

    log_info "Health check completed: $checks_passed/$total_checks checks passed"

    # 過半数のチェックが成功していれば正常とみなす
    if [ $checks_passed -ge $((total_checks / 2)) ]; then
        return 0
    else
        return 1
    fi
}

# メイン監視ループ
main_monitor_loop() {
    log_info "🔍 Camera Health Monitor started"
    log_info "Configuration:"
    log_info "  - Health check interval: ${HEALTH_CHECK_INTERVAL}s"
    log_info "  - Timeout: ${TIMEOUT}s"
    log_info "  - Max consecutive failures: ${MAX_CONSECUTIVE_FAILURES}"

    # 初期待機（サービス起動完了を待つ）
    log_info "Waiting 60 seconds for service startup..."
    sleep 60

    while true; do
        if perform_health_check; then
            consecutive_failures=0
            log_info "Health check passed (consecutive failures reset to 0)"
        else
            ((consecutive_failures++))
            log_error "Health check failed (consecutive failures: $consecutive_failures/$MAX_CONSECUTIVE_FAILURES)"

            if [ $consecutive_failures -ge $MAX_CONSECUTIVE_FAILURES ]; then
                log_error "⚠️ Maximum consecutive failures reached. Camera service appears unhealthy."
                log_error "Exiting to trigger systemd restart..."
                exit 1
            fi
        fi

        log_info "Next health check in ${HEALTH_CHECK_INTERVAL} seconds..."
        sleep "$HEALTH_CHECK_INTERVAL"
    done
}

# シグナルハンドラー
cleanup() {
    log_info "🛑 Camera Health Monitor stopping..."
    exit 0
}

trap cleanup SIGTERM SIGINT

# スクリプト実行
main_monitor_loop
