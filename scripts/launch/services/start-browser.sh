#!/bin/bash

# Browser Service Startup for Coordinate Recorder
# Automatically launches kiosk mode browser on Raspberry Pi for touchscreen interface

set -e

# Source environment loader if not already loaded
if [ -z "$PROJECT_ROOT" ]; then
    source "$(dirname "${BASH_SOURCE[0]}")/../common/load-env.sh"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[BROWSER]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[BROWSER]${NC} $1"
}

print_error() {
    echo -e "${RED}[BROWSER]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[BROWSER]${NC} $1"
}

# Configuration constants
readonly BROWSER_START_WAIT=3
readonly UI_READY_WAIT=5

# Function to detect if running on Raspberry Pi
is_raspberry_pi() {
    # Check hostname pattern
    if [[ $(hostname) == *"pi-camera"* ]] || [[ $(hostname) == *"raspberry"* ]] || [[ $(hostname) == *"pi"* ]]; then
        return 0
    fi

    # Check for Raspberry Pi specific files
    if [ -f /proc/device-tree/model ]; then
        if grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
            return 0
        fi
    fi

    # Check for ARM architecture (common on Pi)
    if [ -f /proc/cpuinfo ]; then
        if grep -qi "arm" /proc/cpuinfo 2>/dev/null; then
            return 0
        fi
    fi

    return 1
}

# Function to detect available display
detect_display() {
    # Check for DISPLAY environment variable
    if [ -n "$DISPLAY" ]; then
        print_status "Using existing DISPLAY: $DISPLAY"
        return 0
    fi

    # Try common display values
    for display in ":0" ":1" ":0.0"; do
        if DISPLAY=$display xset q >/dev/null 2>&1; then
            export DISPLAY=$display
            print_status "Detected DISPLAY: $DISPLAY"
            return 0
        fi
    done

    # Set default display for headless systems
    export DISPLAY=":0"
    print_warning "No display detected, using default: $DISPLAY"
    return 1
}

# Function to kill existing browser processes
cleanup_existing_browsers() {
    print_info "Cleaning up existing browser processes..."

    # Kill Chromium processes
    pkill -f chromium-browser 2>/dev/null || true
    pkill -f chrome 2>/dev/null || true

    # Wait for processes to terminate
    sleep 2

    # Force kill if still running
    pkill -9 -f chromium-browser 2>/dev/null || true
    pkill -9 -f chrome 2>/dev/null || true

    print_status "✅ Browser cleanup completed"
}

# Function to wait for UI server to be ready
wait_for_ui_server() {
    local ui_port=${UI_PORT:-3000}
    local max_attempts=30
    local attempt=1

    print_info "Waiting for UI server on port $ui_port..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s --head --connect-timeout 2 --max-time 5 "http://localhost:${ui_port}" > /dev/null 2>&1; then
            print_status "✅ UI server is ready"
            return 0
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    print_warning "⚠️ UI server not ready after $max_attempts attempts, continuing anyway..."
    return 1
}

# Function to start kiosk browser
start_kiosk_browser() {
    local ui_port=${UI_PORT:-3000}
    local url="${1:-http://localhost:${ui_port}/touchscreen}"

    print_status "🚀 Starting kiosk browser for touchscreen interface..."
    print_info "Target URL: $url"

    # Ensure display is available
    if ! detect_display; then
        print_error "❌ No display available for browser"
        return 1
    fi

    # Clean up existing browsers
    cleanup_existing_browsers

    # Wait for UI server to be ready
    wait_for_ui_server
    sleep $UI_READY_WAIT

    # Create browser configuration
    local user_data_dir="$HOME/.config/chromium-kiosk"
    local log_file="${PROJECT_ROOT}/logs/browser-service.log"

    # Ensure log directory exists
    mkdir -p "${PROJECT_ROOT}/logs"
    mkdir -p "$user_data_dir"

    # Browser launch options
    local browser_opts=(
        --kiosk
        --disable-infobars
        --disable-session-crashed-bubble
        --disable-restore-session-state
        --disable-features=TranslateUI,VizDisplayCompositor
        --no-first-run
        --disable-default-apps
        --disable-popup-blocking
        --disable-prompt-on-repost
        --no-default-browser-check
        --disable-backgrounding-occluded-windows
        --disable-renderer-backgrounding
        --disable-background-timer-throttling
        --user-data-dir="$user_data_dir"
        --start-fullscreen
    )

    # Add web security disable only for development environments
    if [ "${NODE_ENV:-development}" = "development" ]; then
        browser_opts+=(--disable-web-security)
        print_status "🔓 Web security disabled for development environment"
    else
        print_status "🔒 Web security enabled for production environment"
    fi

    # Add touch-specific options if available
    if [ -e /dev/input/touchscreen ] || [ -e /dev/input/event* ]; then
        browser_opts+=(--touch-events=enabled)
        print_status "📱 Touch events enabled"
    fi

    # Start browser in background
    print_status "Launching chromium-browser in kiosk mode..."

    # Use nohup for persistence
    DISPLAY=$DISPLAY nohup chromium-browser "${browser_opts[@]}" "$url" \
        > "$log_file" 2>&1 &
    local browser_pid=$!

    # Wait for browser to start
    sleep $BROWSER_START_WAIT

    # Verify browser is running
    if ps -p $browser_pid > /dev/null 2>&1; then
        # Register with process manager
        local pids_file="${PROJECT_ROOT}/.dev-pids"
        echo "$browser_pid" >> "$pids_file"

        local process_manager="${PROJECT_ROOT}/scripts/process-manager.sh"
        if [ -f "$process_manager" ]; then
            "$process_manager" register "browser" "$browser_pid" "kiosk" "$PROJECT_ROOT"
        fi

        print_status "✅ Kiosk browser started (PID: $browser_pid)"
        print_status "📱 Touchscreen interface available at: $url"
        print_status "📝 Browser logs: $log_file"
        return 0
    else
        print_error "❌ Failed to start kiosk browser, check logs: $log_file"
        return 1
    fi
}

# Function to start regular browser (for development)
start_regular_browser() {
    local ui_port=${UI_PORT:-3000}
    local url="${1:-http://localhost:${ui_port}}"

    print_status "🖥️ Opening regular browser window..."
    print_info "Target URL: $url"

    # Wait for UI server to be ready
    wait_for_ui_server
    sleep 2

    # Try different browsers in order of preference
    local browsers=(
        "chromium-browser"
        "google-chrome"
        "firefox"
        "open"  # macOS
    )

    for browser in "${browsers[@]}"; do
        if command -v "$browser" >/dev/null 2>&1; then
            print_status "Using browser: $browser"

            if [ "$browser" = "open" ]; then
                # macOS
                open "$url"
            else
                # Linux
                "$browser" "$url" &
            fi

            return 0
        fi
    done

    print_error "❌ No suitable browser found"
    return 1
}

# Function to check browser requirements
check_browser_requirements() {
    print_info "Checking browser requirements..."

    # Check for Chromium
    if ! command -v chromium-browser >/dev/null 2>&1; then
        print_warning "⚠️ chromium-browser not found"
        print_info "Install with: sudo apt-get install chromium-browser"
        return 1
    fi

    # Check display capability on Pi
    if is_raspberry_pi; then
        if [ -z "$DISPLAY" ] && ! detect_display; then
            print_warning "⚠️ No display detected on Raspberry Pi"
            print_info "Ensure X server is running: sudo systemctl start lightdm"
            return 1
        fi
    fi

    print_status "✅ Browser requirements satisfied"
    return 0
}

# Main function
main() {
    local mode="${1:-auto}"
    local url="${2:-}"

    case "$mode" in
        "kiosk")
            if ! is_raspberry_pi; then
                print_warning "⚠️ Kiosk mode recommended for Raspberry Pi, starting anyway..."
            fi
            start_kiosk_browser "$url"
            ;;
        "regular"|"window")
            start_regular_browser "$url"
            ;;
        "check")
            check_browser_requirements
            ;;
        "cleanup")
            cleanup_existing_browsers
            ;;
        "auto")
            if is_raspberry_pi; then
                print_status "🍓 Raspberry Pi detected, starting kiosk mode"
                start_kiosk_browser "$url"
            else
                print_status "💻 Regular system detected, starting window mode"
                start_regular_browser "$url"
            fi
            ;;
        *)
            echo "Usage: $0 {auto|kiosk|regular|check|cleanup} [url]"
            echo ""
            echo "Modes:"
            echo "  auto     - Automatically choose mode based on system (default)"
            echo "  kiosk    - Start fullscreen kiosk browser (Raspberry Pi)"
            echo "  regular  - Start regular browser window (development)"
            echo "  check    - Check browser requirements"
            echo "  cleanup  - Clean up existing browser processes"
            echo ""
            echo "Parameters:"
            echo "  url      - Target URL (default: http://localhost:3000/touchscreen for kiosk, / for regular)"
            echo ""
            echo "Examples:"
            echo "  $0                              # Auto-detect mode"
            echo "  $0 kiosk                        # Force kiosk mode"
            echo "  $0 regular http://localhost:3000 # Regular browser with custom URL"
            echo "  $0 check                        # Check requirements"
            exit 1
            ;;
    esac
}

# Execute main if script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
