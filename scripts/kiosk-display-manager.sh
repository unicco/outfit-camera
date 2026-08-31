#!/bin/bash

# Kiosk Display Manager
# Manages screen brightness during Ubuntu startup and touchscreen display

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_ROOT/config/brightness-control.conf"
BRIGHTNESS_SCRIPT="$SCRIPT_DIR/display-brightness.sh"

# ブラウザ PID をグローバルに保持（監視ループで使用）
BROWSER_PID=""

# Load configuration
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
else
    echo "❌ Configuration file not found: $CONFIG_FILE"
    echo "Please ensure the brightness control configuration exists."
    exit 1
fi

# 死活監視（systemd/scripts/kiosk-health-monitor.sh）が読む。監視側がパターンで pgrep すると
# URL のパスに依存して開く画面を変えたときに破綻するため、PID を渡す
BROWSER_PID_FILE="${BROWSER_PID_FILE:-/tmp/kiosk-browser.pid}"
BROWSER_LOCK_FILE="${BROWSER_LOCK_FILE:-/tmp/kiosk-browser.lock}"

# Function to wait for touchscreen to be ready
wait_for_touchscreen() {
    echo "⏳ Waiting for touchscreen to be ready..."
    local max_attempts=${HEALTH_CHECK_MAX_ATTEMPTS:-60}
    local attempt=1
    local timeout=${HEALTH_CHECK_TIMEOUT:-5}
    local url=${UI_URL:-"http://100.64.0.10:3000/touchscreen"}

    while [ $attempt -le $max_attempts ]; do
        if curl -s --max-time "$timeout" --user-agent "Kiosk-Manager/1.0" -o /dev/null -w "%{http_code}" "$url" | grep -q "200"; then
            echo "✅ Touchscreen is ready!"
            return 0
        fi

        echo "   Attempt $attempt/$max_attempts: Touchscreen not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "⚠️ Touchscreen readiness timeout after ${max_attempts} attempts, proceeding anyway..."
    return 1
}

# Function to launch browser in kiosk mode with brightness control
launch_kiosk_browser() {
    # ロックファイルでの重複起動防止
    local lock_file="$BROWSER_LOCK_FILE"
    local lock_timeout=300  # 5分でロックファイルを無効とみなす

    if [ -f "$lock_file" ]; then
        local lock_pid=$(cat "$lock_file" 2>/dev/null)
        local lock_age=$(($(date +%s) - $(stat -c %Y "$lock_file" 2>/dev/null || echo 0)))

        # ロックファイルが古い場合は削除
        if [ "$lock_age" -gt "$lock_timeout" ]; then
            echo "🔓 Removing old lock file (age: ${lock_age}s)"
            rm -f "$lock_file"
        elif [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
            echo "⚠️ Kiosk browser launch already in progress (PID: $lock_pid)"
            return 1
        else
            echo "🔓 Removing stale lock file (process $lock_pid not found)"
            rm -f "$lock_file"
        fi
    fi

    # 現在のプロセスIDをロックファイルに記録
    echo $$ > "$lock_file"
    # 複数のシグナルに対応
    trap "rm -f $lock_file $BROWSER_PID_FILE" EXIT TERM INT HUP

    echo "🌑 Dimming display during startup..."
    "$BRIGHTNESS_SCRIPT" dim

    # Gracefully terminate existing browser processes
    echo "🔄 Terminating existing browser processes..."
    # 全 Chromium プロセスを対象にする（子プロセス含む）
    # 注: "chromium.*--kiosk" だとメインプロセスしかマッチせず、
    # renderer/gpu 等の子プロセスが残りタブが蓄積する問題があった
    local process_pattern=${BROWSER_PROCESS_NAME:-"chromium"}
    local shutdown_delay=${GRACEFUL_SHUTDOWN_DELAY:-3}

    terminate_browser_processes "$process_pattern" "$shutdown_delay" "Chromium"
    # フォールバック: chromium-browser バイナリ名の場合
    terminate_browser_processes "chromium-browser" 2 "Chromium (fallback)"
    # Legacy cleanup for firefox
    terminate_browser_processes "firefox.*--kiosk" 2 "Firefox"

    sleep 2

    # Wait for touchscreen to be ready
    wait_for_touchscreen

    echo "🚀 Launching Chromium in kiosk mode..."

    # Wayland environment setup
    export WAYLAND_DISPLAY=wayland-0
    unset DISPLAY  # Remove X11 display variable for pure Wayland

    local browser_cmd=${BROWSER_COMMAND:-"/usr/bin/chromium"}
    # 注: .env の BROWSER_FLAGS で上書き可能。デバッグ用フラグ（--remote-debugging-port 等）を
    # 残したままにしないよう注意すること
    local browser_flags=${BROWSER_FLAGS:-"--kiosk --no-first-run --disable-infobars --disable-session-crashed-bubble --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-features=TranslateUI,VizDisplayCompositor --disable-dev-shm-usage --no-sandbox --enable-features=UseOzonePlatform --ozone-platform=wayland --disable-gpu-sandbox --disable-software-rasterizer --noerrdialogs --disable-translate --disable-restore-session-state --block-new-web-contents"}
    local startup_delay=${BROWSER_STARTUP_DELAY:-10}
    local url=${UI_URL:-"http://100.64.0.10:3000/touchscreen"}

    # セッション復元を防止するため、起動ごとにクリーンなプロファイルを使用
    # これにより異常終了後のタブ復元（蓄積の主原因）を防ぐ
    local kiosk_profile="/tmp/chromium-kiosk-profile"
    # シンボリックリンク攻撃を防止するためパスを検証してから削除
    if [[ -e "$kiosk_profile" && "$kiosk_profile" == /tmp/* ]]; then
        rm -rf "$kiosk_profile"
    fi
    mkdir -p "$kiosk_profile"

    # BROWSER_FLAGS に --user-data-dir が含まれていない場合のみ追加
    if [[ "$browser_flags" != *"--user-data-dir"* ]]; then
        browser_flags="$browser_flags --user-data-dir=\"$kiosk_profile\""
    fi

    # Launch Chromium in background with proper Wayland environment
    echo "🔗 Launching with URL: $url"
    echo "🔧 Browser command: $browser_cmd $browser_flags $url"
    env WAYLAND_DISPLAY=wayland-0 $browser_cmd $browser_flags "$url" > /tmp/chromium-kiosk.log 2>&1 &
    local browser_pid=$!
    BROWSER_PID=$browser_pid
    echo "$browser_pid" > "$BROWSER_PID_FILE"

    # Give browser time to load
    echo "   Waiting ${startup_delay}s for Chromium to load..."
    sleep "$startup_delay"

    # Check if Chromium process is still running
    if ! kill -0 "$browser_pid" 2>/dev/null; then
        echo "⚠️ Chromium process may have failed. Log output:"
        cat /tmp/chromium-kiosk.log 2>/dev/null || echo "No log available"
    fi

    # Wayland-specific window management (labwc integration)
    if command -v labwc-menu-generator >/dev/null 2>&1; then
        echo "🔄 Refreshing labwc compositor..."
        WAYLAND_DISPLAY=wayland-0 labwc-menu-generator 2>/dev/null || true
    fi

    echo "🌞 Brightening display for touchscreen..."
    "$BRIGHTNESS_SCRIPT" bright

    echo "✅ Kiosk display manager setup complete"
}

# Enhanced process termination with timeout monitoring
terminate_browser_processes() {
    local process_pattern="$1"
    local timeout_seconds="$2"
    local process_name="$3"

    echo "🔄 Terminating $process_name processes..."

    # Check if any processes match the pattern
    if ! pgrep -f "$process_pattern" > /dev/null 2>&1; then
        echo "   No $process_name processes found"
        return 0
    fi

    # Send SIGTERM for graceful shutdown
    echo "   Sending SIGTERM to $process_name processes..."
    pkill -TERM -f "$process_pattern" > /dev/null 2>&1 || true

    # Wait with timeout monitoring
    local elapsed=0
    local check_interval=0.5

    while [ $elapsed -lt $timeout_seconds ]; do
        if ! pgrep -f "$process_pattern" > /dev/null 2>&1; then
            echo "   ✅ $process_name processes terminated gracefully (${elapsed}s)"
            return 0
        fi

        sleep $check_interval
        elapsed=$(echo "$elapsed + $check_interval" | bc 2>/dev/null || echo $((elapsed + 1)))
    done

    # Force kill if timeout exceeded
    echo "   ⚠️ Graceful shutdown timeout (${timeout_seconds}s), force killing..."
    local kill_count=$(pgrep -f "$process_pattern" | wc -l)
    pkill -KILL -f "$process_pattern" > /dev/null 2>&1 || true

    # Verify force kill worked
    sleep 0.5
    if pgrep -f "$process_pattern" > /dev/null 2>&1; then
        echo "   ❌ Failed to terminate some $process_name processes"
        pgrep -f "$process_pattern" | while read pid; do
            echo "      Remaining PID: $pid"
        done
        return 1
    else
        echo "   ✅ Force killed $kill_count $process_name processes"
        return 0
    fi
}

# Function to handle shutdown
cleanup() {
    echo "🧹 Cleaning up kiosk display manager..."
    local shutdown_delay=${GRACEFUL_SHUTDOWN_DELAY:-3}

    rm -f "$BROWSER_PID_FILE"

    # Terminate browser processes with enhanced monitoring
    # 全 Chromium プロセスを対象（子プロセス含む）
    local process_pattern=${BROWSER_PROCESS_NAME:-"chromium"}
    terminate_browser_processes "$process_pattern" "$shutdown_delay" "Chromium"

    # フォールバック: より広範囲なパターンで確実に終了
    terminate_browser_processes "chromium-browser" 2 "Chromium (fallback)"

    # Also clean up any remaining firefox processes
    terminate_browser_processes "firefox.*--kiosk" 2 "Firefox"

    # Dim display
    echo "🌑 Dimming display..."
    if ! "$BRIGHTNESS_SCRIPT" dim; then
        echo "⚠️ Failed to dim display"
    fi

    echo "✅ Cleanup complete"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

case "$1" in
    "start")
        launch_kiosk_browser
        # Keep script running for systemd Type=simple with enhanced monitoring
        while true; do
            sleep 60
            # Check if browser is still running (PID ベースで正確に監視)
            if [ -n "$BROWSER_PID" ] && ! kill -0 "$BROWSER_PID" 2>/dev/null; then
                echo "⚠️ Browser process (PID: $BROWSER_PID) not found, exiting..."
                exit 1
            fi

            # Check if touchscreen UI is accessible (recovery mechanism)
            check_interval=120  # Check every 2 minutes
            if [ $(($(date +%s) % check_interval)) -eq 0 ]; then
                echo "🔍 Performing touchscreen accessibility check..."
                if ! curl -s --max-time 5 --user-agent "Kiosk-Monitor/1.0" -o /dev/null -w "%{http_code}" "${UI_URL:-http://100.64.0.10:3000/touchscreen}" | grep -q "200"; then
                    echo "⚠️ Touchscreen UI not accessible, may need attention"
                    # Log the issue but don't restart automatically to avoid loops
                    echo "$(date): Touchscreen UI accessibility check failed" >> /tmp/kiosk-monitor.log
                fi
            fi
        done
        ;;
    "stop")
        cleanup
        ;;
    "restart")
        cleanup
        sleep 2
        launch_kiosk_browser
        ;;
    *)
        echo "Usage: $0 [start|stop|restart]"
        echo "  start   - Launch kiosk browser with brightness control"
        echo "  stop    - Stop browser and dim display"
        echo "  restart - Restart browser with brightness control"
        exit 1
        ;;
esac
