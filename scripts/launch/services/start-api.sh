#!/bin/bash

# API Service Startup
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
    echo -e "${GREEN}[API]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[API]${NC} $1"
}

print_error() {
    echo -e "${RED}[API]${NC} $1"
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

# Extract ports from environment variables
extract_port() {
    echo "$1" | sed -E 's/.*:([0-9]+).*/\1/'
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

    # Python service - use virtual environment
    local python_cmd="python"
    local venv_activate=""
    local venv_found=false

    # Priority 1: Use VENV_PATH if explicitly set
    if [ -n "$VENV_PATH" ] && [ -f "$VENV_PATH/bin/activate" ]; then
        venv_activate="source \"$VENV_PATH/bin/activate\" &&"
        print_status "🐍 Using custom virtual environment: $VENV_PATH"
        venv_found=true
    # Priority 2: Search using VENV_SEARCH_PATTERNS
    elif [ -n "$VENV_SEARCH_PATTERNS" ]; then
        IFS=',' read -ra PATTERNS <<< "$VENV_SEARCH_PATTERNS"
        for pattern in "${PATTERNS[@]}"; do
            # Handle glob patterns
            for venv_dir in $pattern; do
                if [ -f "$venv_dir/bin/activate" ]; then
                    venv_activate="source \"$venv_dir/bin/activate\" &&"
                    print_status "🐍 Found virtual environment: $venv_dir"
                    venv_found=true
                    break 2
                fi
            done
        done
    fi

    # Priority 3: Check for local venv directory
    if [ "$venv_found" = false ]; then
        if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
            venv_activate="source venv/bin/activate &&"
            print_status "🐍 Using local virtual environment: $(pwd)/venv"
        else
            print_warning "⚠️ No virtual environment found, using system Python"
        fi
    fi

    # Start Python service with appropriate environment
    # Set PYTHONPATH relative to the service directory
    local pythonpath_export="export PYTHONPATH=\"../src:.\${PYTHONPATH:+:\${PYTHONPATH}}\""
    
    # Export all environment variables for the subprocess
    local env_exports=""
    for var in ROBOFLOW_KEY ROBOFLOW_WORKSPACE GOOGLE_AI_STUDIO_API_KEY GEMINI_API_KEY JINA_API_KEY GCS_BUCKET_NAME GCS_PROJECT_ID GOOGLE_APPLICATION_CREDENTIALS STORAGE_TYPE DATABASE_URL; do
        if [ -n "${!var}" ]; then
            env_exports="$env_exports export $var=\"${!var}\";"
        fi
    done

    if [ -n "$venv_activate" ]; then
        # Use nohup for process persistence with virtual environment
        nohup bash -c "$venv_activate $env_exports $pythonpath_export && $command" > "$log_file" 2>&1 &
        local pid=$!
    else
        # Use nohup for process persistence with system environment
        nohup bash -c "$env_exports $pythonpath_export && $command" > "$log_file" 2>&1 &
        local pid=$!
    fi

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

# Start API Server
start_api_server() {
    # Extract API port from environment
    local api_port=$(extract_port "$VITE_API_URL")
    api_port=${api_port:-8000}

    print_status "🚀 Starting API Server on port $api_port..."

    # Clean up any existing processes on the API port
    cleanup_port "$api_port" "API Server"

    # Start API Server
    start_service "API Server" \
        "python -m uvicorn app.main:app --host 0.0.0.0 --port $api_port --reload" \
        "${PROJECT_ROOT}/api" \
        "$api_port"

    return $?
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    start_api_server
fi
