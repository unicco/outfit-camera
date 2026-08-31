#!/bin/bash

# Kiosk Health Monitor
# キオスクブラウザの状態を監視し、必要に応じて再起動

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# 共通ログ関数を読み込み
source "$SCRIPT_DIR/common-logging.sh"

log_info "Starting kiosk health monitor..."

# キオスク本体（kiosk-display-manager.sh）と同じ conf から UI_URL を取る。
# conf は `${VAR:-...}` 形なので systemd の Environment / EnvironmentFile が優先される。
# ここを読まないと「ブラウザが開く URL」と「監視が叩く URL」がずれる
CONFIG_FILE="$PROJECT_ROOT/config/brightness-control.conf"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    log_warn "Configuration file not found: $CONFIG_FILE (falling back to built-in defaults)"
fi
UI_URL="${UI_URL:-http://100.64.0.10:3000/touchscreen}"
BROWSER_COMMAND="${BROWSER_COMMAND:-/usr/bin/chromium}"

# ブラウザ生存監視の設定
# 一次情報は kiosk-display-manager.sh が書く PID ファイル。URL のパターンで pgrep すると
# 開く画面を変えたときに破綻する
BROWSER_PID_FILE="${BROWSER_PID_FILE:-/tmp/kiosk-browser.pid}"
BROWSER_MISSING_COUNT=0
# キオスクのブラウザを見分けるパターン。バイナリ名と `--kiosk`（BROWSER_FLAGS が必ず
# 持つ）で引き、URL には依存させない。URL のパスで引くと開く画面を変えたときに破綻する。
# PID の照合とプロセス探索で同じものを使う（別々に持つと片方だけずれる）
BROWSER_BINARY_NAME="$(basename "$BROWSER_COMMAND")"
KIOSK_BROWSER_PATTERN="$BROWSER_BINARY_NAME.*--kiosk"

# kiosk-display-manager.sh が起動処理の先頭で作るロック。UI が不通のとき
# wait_for_touchscreen が 3 分以上ブロックするので、その間は生存判定を保留する。
# 保留しないと、待っている最中に restart を打って待ちを振り出しに戻し続ける
# ⚠️ このロックは display manager の持ち物。古い分は向こうが自分で捨てるので消さない
BROWSER_LOCK_FILE="${BROWSER_LOCK_FILE:-/tmp/kiosk-browser.lock}"
LAUNCH_GRACE_MINUTES=5

# PID の生存だけでは足りない。ブラウザ終了後に同じ PID が別プロセスへ再利用されると
# 永久に「生きている」と答え、本物の異常を検出できなくなる
browser_pid_alive() {
    local pid
    pid=$(cat "$BROWSER_PID_FILE" 2>/dev/null) || return 1
    [ -n "$pid" ] || return 1
    ps -p "$pid" -o command= 2>/dev/null | grep -q "$KIOSK_BROWSER_PATTERN"
}

kiosk_launch_in_progress() {
    [ -f "$BROWSER_LOCK_FILE" ] || return 1
    [ -n "$(find "$BROWSER_LOCK_FILE" -mmin -"$LAUNCH_GRACE_MINUTES" 2>/dev/null)" ]
}

# Camera stream monitoring configuration
CAMERA_URL="${CAMERA_URL:-http://localhost:8001}"
STREAM_FAILURE_COUNT=0
STREAM_RESTART_COOLDOWN=0
CAMERA_RESTART_LOG="/tmp/.camera-restart-log"

# /stream の MJPEG multipart ヘッダが 5 秒以内に届くかをチェック
# bytes 数ではなく Content-Type: image/jpeg の到達でフレーム配信中を判定する
check_camera_stream_serving() {
    curl -s -i --max-time 5 "$CAMERA_URL/stream" 2>/dev/null \
        | head -c 8192 \
        | grep -q -i "Content-Type: image/jpeg"
}

# 直近 24 時間の再起動回数を取得（rate limit 用）
camera_restart_count_last_24h() {
    local now cutoff
    now=$(date +%s)
    cutoff=$((now - 86400))
    [ -f "$CAMERA_RESTART_LOG" ] || { echo 0; return; }
    awk -v c="$cutoff" '$1 >= c' "$CAMERA_RESTART_LOG" | wc -l | tr -d ' '
}

# 再起動ログに timestamp を記録（古いエントリは削除）
record_camera_restart() {
    local now cutoff tmpfile
    now=$(date +%s)
    cutoff=$((now - 86400))
    tmpfile=$(mktemp)
    if [ -f "$CAMERA_RESTART_LOG" ]; then
        awk -v c="$cutoff" '$1 >= c' "$CAMERA_RESTART_LOG" > "$tmpfile"
    fi
    echo "$now" >> "$tmpfile"
    mv "$tmpfile" "$CAMERA_RESTART_LOG"
}

while true; do
    # 1. キオスクサービスの状態確認
    if ! systemctl is-active --quiet coordinate-kiosk.service; then
        log_error "Kiosk service is not active, attempting to start..."
        sudo systemctl start coordinate-kiosk.service
        sleep 10
    fi

    # 2. ブラウザプロセスの確認
    # PID ファイルと実プロセスの両方が不在のときだけ再起動する。片方だけの不一致は
    # 手動起動や PID ファイルの取りこぼしなので、警告に留めて画面を触らない
    if browser_pid_alive; then
        BROWSER_MISSING_COUNT=0
    elif kiosk_launch_in_progress; then
        log_debug "Kiosk launch in progress; deferring browser check"
        BROWSER_MISSING_COUNT=0
    elif pgrep -f "$KIOSK_BROWSER_PATTERN" >/dev/null 2>&1; then
        log_warn "Browser PID file is stale but $BROWSER_BINARY_NAME is running; skipping restart"
        BROWSER_MISSING_COUNT=0
    else
        BROWSER_MISSING_COUNT=$((BROWSER_MISSING_COUNT + 1))
        log_warn "Kiosk browser process not found (${BROWSER_MISSING_COUNT}/3 before restart)"

        # キオスク本体も自分の監視ループと Restart=always で復帰を試みるので、後詰めで待つ
        if [ "$BROWSER_MISSING_COUNT" -ge 3 ]; then
            log_error "Kiosk browser missing for 3 cycles, restarting coordinate-kiosk.service"
            sudo systemctl restart coordinate-kiosk.service
            BROWSER_MISSING_COUNT=0
            sleep 15
        fi
    fi

    # 3. UI の可用性確認
    # UI は VPS 配信。落ちていても Pi 側でできることがないので警告だけ出す。
    # 復帰後の画面はブラウザが自分で戻す。Chromium はネットワーク層エラーのページを
    # 標準で自動リロードする（バックオフ上限 30 分）ので、リロードや restart を
    # ここに再実装しない（実測と根拠は）
    if ! curl -fs --max-time "${HEALTH_CHECK_TIMEOUT:-5}" "$UI_URL" >/dev/null 2>&1; then
        log_warn "UI not responding: $UI_URL"
    else
        log_debug "Kiosk display health check passed"
    fi

    # 4. ディスプレイの状態確認（オプション）
    if command -v xset >/dev/null 2>&1; then
        if ! DISPLAY=:0 timeout 2 xset q >/dev/null 2>&1; then
            log_warn "Display connection issue detected"
        fi
    fi

    # 5. カメラ MJPEG ストリームの可用性確認
    # /health は応答するが /stream がフリーズしているケースを拾う
    # 連続 3 サイクル失敗で coordinate-camera.service を再起動（24h で 4 回まで）
    if ! check_camera_stream_serving; then
        STREAM_FAILURE_COUNT=$((STREAM_FAILURE_COUNT + 1))
        log_warn "Camera stream check failed (${STREAM_FAILURE_COUNT}/3 before restart)"

        if [ "$STREAM_FAILURE_COUNT" -ge 3 ] && [ "$STREAM_RESTART_COOLDOWN" -le 0 ]; then
            recent_restarts=$(camera_restart_count_last_24h)
            if [ "$recent_restarts" -ge 4 ]; then
                log_error "Camera service restart rate-limited (${recent_restarts} restarts in last 24h, max 4); skipping"
                STREAM_FAILURE_COUNT=0
                STREAM_RESTART_COOLDOWN=10
            else
                log_error "Camera stream unhealthy for 3 cycles, restarting coordinate-camera.service (${recent_restarts}/4 in last 24h)"
                if sudo -n systemctl restart coordinate-camera.service 2>/dev/null; then
                    log_info "Camera service restart issued"
                    record_camera_restart
                else
                    log_error "sudo systemctl restart coordinate-camera.service failed (check /etc/sudoers.d/010_pi-nopasswd)"
                fi
                STREAM_FAILURE_COUNT=0
                STREAM_RESTART_COOLDOWN=10
            fi
        fi
    else
        STREAM_FAILURE_COUNT=0
    fi

    if [ "$STREAM_RESTART_COOLDOWN" -gt 0 ]; then
        STREAM_RESTART_COOLDOWN=$((STREAM_RESTART_COOLDOWN - 1))
    fi

    # 60秒待機
    sleep 60
done
