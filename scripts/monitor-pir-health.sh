#!/bin/bash

# PIR センサー健康状態監視スクリプト
# カメラサービスが正常に動作し、PIR 検知が機能していることを確認

CAMERA_URL="${CAMERA_URL:-http://localhost:8001}"
LOG_FILE="${LOG_FILE:-/home/pi/coordinate-recorder/logs/pir-monitor.log}"
CHECK_INTERVAL_MINUTES="${CHECK_INTERVAL_MINUTES:-1}"  # 1分毎にチェック
MAX_SILENCE_HOURS_WARNING="${MAX_SILENCE_HOURS_WARNING:-8}"  # 8時間無音で警告
MAX_SILENCE_HOURS_RESTART="${MAX_SILENCE_HOURS_RESTART:-12}"  # 12時間無音で再起動

# ログ関数
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# 基本ヘルスチェックは monitor-camera-health.sh に任せ、こちらは PIR 特化監視に集中

# PIR ステータスチェック
check_pir_status() {
    local pir_response=$(curl -s --max-time 5 "$CAMERA_URL/pir/status" 2>/dev/null)

    if [ $? -eq 0 ]; then
        local enabled=$(echo "$pir_response" | grep -o '"enabled":[^,]*' | cut -d: -f2)
        local detections=$(echo "$pir_response" | grep -o '"detections_count":[^,]*' | cut -d: -f2)

        if [ "$enabled" = "true" ]; then
            log_message "✅ PIR sensor is enabled (detections: $detections)" >&2
            # 数値のみを返す（ログメッセージは stderr に出力）
            echo "$detections"
            return 0
        else
            log_message "❌ PIR sensor is disabled" >&2
            echo "0"  # 無効化されている場合は 0 を返す
            return 1
        fi
    else
        log_message "❌ PIR status check failed" >&2
        echo "0"  # エラーの場合も 0 を返す
        return 1
    fi
}

# カメラサービス再起動
restart_camera_service() {
    log_message "🔄 Restarting camera service..."

    # 現在のプロセスを停止
    pkill -f camera_service.py
    sleep 3

    # systemd サービスを使用して再起動
    sudo systemctl restart coordinate-camera.service
    sleep 10

    # PIR ステータスで確認
    if check_pir_status > /dev/null 2>&1; then
        log_message "✅ Camera service restarted successfully"
        return 0
    else
        log_message "❌ Camera service restart failed"
        return 1
    fi
}

# メイン監視ループ
main() {
    log_message "🔍 Starting PIR health monitoring..."

    local last_detection_count=0
    local silence_start_time=$(date +%s)

    while true; do
        # PIR ステータスチェック（PIR 動作パターンに特化した監視）
        local current_detections=$(check_pir_status)

        if [ $? -eq 0 ]; then
            if [ "$current_detections" -gt "$last_detection_count" ]; then
                # 新しい検知があった
                log_message "🎯 New PIR detection detected (total: $current_detections)"
                last_detection_count=$current_detections
                silence_start_time=$(date +%s)
            else
                # 無音時間をチェック
                local current_time=$(date +%s)
                local silence_duration_hours=$(( (current_time - silence_start_time) / 3600 ))

                if [ $silence_duration_hours -ge $MAX_SILENCE_HOURS_WARNING ]; then
                    log_message "⚠️ PIR sensor has been silent for $silence_duration_hours hours"

                    # 12時間無音の場合はサービス再起動
                    if [ $silence_duration_hours -ge $MAX_SILENCE_HOURS_RESTART ]; then
                        log_message "🔄 Extended silence ($silence_duration_hours hours) detected, restarting camera service..."
                        restart_camera_service
                        silence_start_time=$(date +%s)
                    fi
                fi
            fi
        fi

        # 10分待機
        sleep $((CHECK_INTERVAL_MINUTES * 60))
    done
}

# スクリプト実行
main "$@"
