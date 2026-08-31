#!/bin/bash

# UI Service Startup
# Extracted from start-dev.sh for modular architecture

set -e

# Source environment loader if not already loaded
if [ -z "$PROJECT_ROOT" ]; then
    source "$(dirname "${BASH_SOURCE[0]}")/../common/load-env.sh"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[UI]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[UI]${NC} $1"
}

print_error() {
    echo -e "${RED}[UI]${NC} $1"
}

# Configuration constants
readonly GRACEFUL_SHUTDOWN_WAIT=2
readonly PORT_CLEANUP_WAIT=1
readonly PROCESS_START_WAIT=1

# Function to check if port is available
check_port() {
    local port=$1
    if lsof -i :$port > /dev/null 2>&1; then
        return 1  # Port is busy
    else
        return 0  # Port is available
    fi
}

# Clean up port conflicts
cleanup_port() {
    local port=$1
    local service_name=$2

    if [ -n "$port" ] && ! check_port $port; then
        print_warning "Port $port is busy, attempting to free it for $service_name..."
        # Get PIDs first, then kill them atomically to avoid race condition
        pids=$(lsof -ti :$port 2>/dev/null || true)
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill -TERM 2>/dev/null || true
            sleep $GRACEFUL_SHUTDOWN_WAIT
            # Force kill if still running
            remaining_pids=$(lsof -ti :$port 2>/dev/null || true)
            if [ -n "$remaining_pids" ]; then
                echo "$remaining_pids" | xargs kill -KILL 2>/dev/null || true
            fi
        fi
        sleep $PORT_CLEANUP_WAIT
    fi
}

# Function to start service in background with persistence
start_service() {
    local name=$1
    local command=$2
    local directory=$3
    local port=$4

    print_status "🔄 Starting $name..."

    cd "$directory"

    # Create logs directory if it doesn't exist (with race condition protection)
    mkdir -p /tmp/coordinate-recorder-locks
    (
        flock -x 200
        mkdir -p "${PROJECT_ROOT}/logs"
    ) 200>/tmp/coordinate-recorder-locks/logs-dir.lock
    local log_file="${PROJECT_ROOT}/logs/$(echo ${name} | tr '[:upper:]' '[:lower:]')-service.log"

    # Node.js service - no virtual environment needed
    print_status "🌐 Starting Node.js service: $name"
    nohup bash -c "export PATH=\"\$PATH:/usr/local/bin\" && $command" > "$log_file" 2>&1 &
    local pid=$!

    # Wait a moment for process to start
    sleep $PROCESS_START_WAIT

    # Verify process is still running
    if ps -p $pid > /dev/null 2>&1; then
        # Register with legacy system (with race condition protection)
        local pids_file="${PROJECT_ROOT}/.dev-pids"
        (
            flock -x 200
            echo "$pid" >> "$pids_file"
        ) 200>/tmp/coordinate-recorder-locks/legacy-pids.lock

        # Register with process manager if available
        local process_manager="${PROJECT_ROOT}/scripts/process-manager.sh"
        if [ -f "$process_manager" ]; then
            local service_id="$(echo ${name} | tr '[:upper:]' '[:lower:]' | tr ' ' '-')"
            "$process_manager" register "$service_id" "$pid" "$port" "$PROJECT_ROOT"
        fi

        print_status "✅ $name started (PID: $pid) on port $port"
        print_status "📝 Logs: $log_file"
        return 0
    else
        print_error "❌ $name failed to start, check logs: $log_file"
        return 1
    fi
}

# Start UI Server
start_ui_server() {
    # Use UI_PORT from environment
    local ui_port=${UI_PORT:-3000}

    # Check for fast mode environment variable
    local dev_command="npm run dev"
    if [ "${UI_FAST_MODE:-false}" = "true" ]; then
        dev_command="npm run dev:fast"
        print_status "⚡ Fast mode enabled - TypeScript checks minimized"
    fi

    print_status "🚀 Starting UI Server on port $ui_port..."

    # Clean up any existing processes on the UI port
    cleanup_port "$ui_port" "UI Server"

    # Start UI Server
    start_service "UI Server" \
        "$dev_command -- --host 0.0.0.0 --port $ui_port" \
        "${PROJECT_ROOT}/ui" \
        "$ui_port"

    return $?
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    start_ui_server
fi
