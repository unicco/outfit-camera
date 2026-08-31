#!/bin/bash

# CLAUDE.md Auto-Configuration Shutdown Script
# Issue #187: Clean shutdown of all development services

############################################################
# 警告: このスクリプトは将来的に廃止予定です
#
# systemd への移行を推奨します：
#   - 本番環境: sudo systemctl stop coordinate-*.service
#   - 開発環境: systemd/scripts/stop-services.sh
#
# 詳細: scripts/dev/README.md
############################################################

echo "⚠️  警告: このスクリプトは廃止予定です。systemd の使用を推奨します。" >&2
echo ""

set +e  # Allow errors (processes may not exist)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[COORDINATOR]${NC} $1"
}

# Auto-detect project root and initialize process manager
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDS_FILE="${PROJECT_ROOT}/.dev-pids"
PROCESS_MANAGER="${PROJECT_ROOT}/scripts/process-manager.sh"

print_header "🛑 Stopping Coordinate Recorder Development Environment"

# Use enhanced process manager if available
if [ -f "$PROCESS_MANAGER" ]; then
    print_status "🔧 Using enhanced process manager..."

    # Stop all services managed by this project
    if "$PROCESS_MANAGER" list | grep -q "$(basename "$PROJECT_ROOT")"; then
        print_status "📋 Stopping services for $(basename "$PROJECT_ROOT")..."

        # Stop services by checking project match
        current_project_root="$PROJECT_ROOT"
        for pid_file in /tmp/coordinate-recorder-pids/*.pid; do
            if [ -f "$pid_file" ]; then
                # Safely source PID file with error handling
                if source "$pid_file" 2>/dev/null && [ -n "$PROJECT_ROOT" ]; then
                    # Compare the current project root with the one from PID file
                    if [ "$current_project_root" = "$PROJECT_ROOT" ]; then
                        local service_name=$(basename "$pid_file" .pid)
                        "$PROCESS_MANAGER" stop "$service_name"
                    fi
                else
                    print_warning "⚠️ Invalid PID file: $pid_file, removing..."
                    rm -f "$pid_file"
                fi
            fi
        done
    else
        print_status "ℹ️ No services found for this project"
    fi

    # Clean up any dead services
    "$PROCESS_MANAGER" cleanup
else
    print_warning "⚠️ Enhanced process manager not found, using legacy method"
fi

# === 環境変数統合システム ===
# Load environment variables to get correct ports for cleanup
load_environment() {
    # Load common environment variables first
    if [ -f "$PROJECT_ROOT/.env.common" ]; then
        set -a  # automatically export all variables
        source "$PROJECT_ROOT/.env.common" 2>/dev/null || true
        set +a
    fi

    # Load session-specific environment variables (higher priority)
    if [ -f "$PROJECT_ROOT/.env" ]; then
        set -a  # automatically export all variables
        source "$PROJECT_ROOT/.env" 2>/dev/null || true
        set +a
    fi

    # Use default ports if not set via .env
    export API_PORT=${API_PORT:-8000}
    export UI_PORT=${UI_PORT:-3000}
    export CAMERA_PORT=${CAMERA_PORT:-8001}
    export POSTGRES_PORT=${POSTGRES_PORT:-5432}

    print_status "🔧 Using ports: API=$API_PORT, UI=$UI_PORT, Camera=$CAMERA_PORT"
}

# Load environment for port cleanup
load_environment

# Function to stop process by PID with improved handling
stop_process() {
    local pid=$1
    if ps -p $pid > /dev/null 2>&1; then
        # Get process info for logging
        local process_info=$(ps -p $pid -o comm=,args= 2>/dev/null | head -1)
        print_status "Stopping process $pid ($process_info)..."

        # Try graceful shutdown first (SIGTERM)
        kill -TERM $pid 2>/dev/null || true

        # Wait up to 10 seconds for graceful shutdown
        local count=0
        while ps -p $pid > /dev/null 2>&1 && [ $count -lt 10 ]; do
            sleep 1
            ((count++))
        done

        # If still running, try SIGINT
        if ps -p $pid > /dev/null 2>&1; then
            print_warning "Graceful shutdown failed, sending SIGINT to process $pid..."
            kill -INT $pid 2>/dev/null || true
            sleep 2
        fi

        # Force kill if still running (SIGKILL)
        if ps -p $pid > /dev/null 2>&1; then
            print_warning "Force killing process $pid..."
            kill -9 $pid 2>/dev/null || true
            sleep 1
        fi

        # Final verification
        if ps -p $pid > /dev/null 2>&1; then
            print_error "❌ Failed to stop process $pid"
            return 1
        else
            print_status "✅ Process $pid stopped successfully"
        fi
    else
        print_warning "Process $pid was not running"
    fi
}

# Stop processes from PID file
if [ -f "$PIDS_FILE" ]; then
    print_status "📝 Reading PIDs from $PIDS_FILE"

    while IFS= read -r pid; do
        if [ -n "$pid" ] && [ "$pid" != "" ]; then
            stop_process "$pid"
        fi
    done < "$PIDS_FILE"

    # Clean up PID file
    rm -f "$PIDS_FILE"
    print_status "🧹 Cleaned up PID file"
else
    print_warning "No PID file found, attempting to stop by port..."
fi

# Stop any remaining processes on our ports
print_status "🔍 Checking for remaining processes on ports $UI_PORT, $API_PORT, $CAMERA_PORT..."

for port in $UI_PORT $API_PORT $CAMERA_PORT; do
    pids=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        print_warning "Found processes on port $port: $pids"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        print_status "✅ Cleaned up port $port"
    fi
done


# Issue 260 対応: Chromium/Browser プロセスクリーンアップ
print_status "🌐 Issue 260対応: Checking for browser processes..."

chromium_pids=$(pgrep -f "chrome|chromium|playwright" 2>/dev/null || true)
if [ -n "$chromium_pids" ]; then
    print_warning "Found browser processes: $chromium_pids"
    print_status "🧹 Cleaning up browser processes (Issue 260対応)..."

    # SIGTERM で graceful shutdown を試行
    echo "$chromium_pids" | xargs -r kill -TERM 2>/dev/null || true
    sleep 3

    # まだ残っているプロセスをチェック
    remaining_pids=$(pgrep -f "chrome|chromium|playwright" 2>/dev/null || true)
    if [ -n "$remaining_pids" ]; then
        print_warning "Some browser processes still running, force killing..."
        echo "$remaining_pids" | xargs -r kill -KILL 2>/dev/null || true
        sleep 1

        # 最終確認
        final_pids=$(pgrep -f "chrome|chromium|playwright" 2>/dev/null || true)
        if [ -n "$final_pids" ]; then
            print_warning "⚠️  Some browser processes may still be running"
        else
            print_status "✅ All browser processes cleaned up"
        fi
    else
        print_status "✅ Browser processes gracefully terminated"
    fi
else
    print_status "✅ No browser processes found"
fi

# Verify all ports are free
print_status "🏥 Verifying all ports are free..."
all_clear=true

for port in $UI_PORT $API_PORT $CAMERA_PORT; do
    if lsof -i :$port > /dev/null 2>&1; then
        print_error "❌ Port $port is still busy"
        all_clear=false
    else
        print_status "✅ Port $port is free"
    fi
done

# Clean up log files if requested
if [ "$1" = "--clean-logs" ]; then
    print_status "🧹 Cleaning up log files..."
    if [ -d "${PROJECT_ROOT}/logs" ]; then
        rm -f "${PROJECT_ROOT}/logs"/*-service.log
        print_status "✅ Log files cleaned"
    fi
fi

if [ "$all_clear" = true ]; then
    print_header "🎉 All services stopped successfully!"
    print_status "All ports ($UI_PORT, $API_PORT, $CAMERA_PORT) are now free"
    print_status ""
    print_status "💡 Tips:"
    print_status "  • Use './scripts/start-development.sh' to restart services"
    print_status "  • Use '--clean-logs' flag to remove log files during shutdown"
    print_status "  • Check './scripts/debug/check-ports.sh' for port monitoring"
else
    print_error "⚠️  Some ports may still be busy. Check manually if needed."
    print_status "Use './scripts/debug/check-ports.sh' for detailed port analysis"
    exit 1
fi
