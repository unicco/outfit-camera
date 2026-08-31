#!/bin/bash

# Camera Service Startup
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
    echo -e "${GREEN}[CAMERA]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[CAMERA]${NC} $1"
}

print_error() {
    echo -e "${RED}[CAMERA]${NC} $1"
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

    # Python service - Camera service needs system Python for Picamera2
    local python_cmd="python3"
    local venv_activate=""

    # Camera service requires system Python for Picamera2 access
    print_status "🐍 Using system Python for Camera service (required for Picamera2)"

    # Install Python dependencies to system if needed
    local required_packages="fastapi uvicorn httpx opencv-python numpy pillow python-multipart requests gpiozero"
    print_status "📦 Ensuring required packages are available..."

    # Export critical environment variables for camera service
    local env_vars=""
    for var in CAMERA_MODE API_URL BACKEND_API_URL VITE_API_URL VITE_CAMERA_URL PHOTOS_DIR CAMERA_PORT \
               PIR_ENABLED PIR_GPIO_PIN PIR_DETECTION_THRESHOLD PIR_DETECTION_WINDOW CAMERA_ACTIVE_DURATION \
               PIR_SIMULATION_MODE EDGE_FILTER_ENABLED CAMERA_VFLIP CAMERA_HFLIP \
               CAMERA_DETECTION_WIDTH CAMERA_DETECTION_HEIGHT CAMERA_CAPTURE_WIDTH CAMERA_CAPTURE_HEIGHT \
               STORAGE_TYPE GCS_BUCKET_NAME GCS_PROJECT_ID GOOGLE_APPLICATION_CREDENTIALS \
               THERMAL_MONITOR_INTERVAL THERMAL_LIGHT_THROTTLE THERMAL_HEAVY_THROTTLE THERMAL_RECOVERY \
               STREAMING_FPS CAMERA_AWB_RED_GAIN CAMERA_AWB_BLUE_GAIN DISPLAY_ON_DURATION; do
        if [ -n "${!var}" ]; then
            env_vars="$env_vars export $var=\"${!var}\"; "
        fi
    done

    # Start Python service with system environment (required for Picamera2)
    nohup bash -c "$env_vars export PYTHONPATH=\"${PROJECT_ROOT}/src:\${PYTHONPATH}\" && $python_cmd ${command#python }" > "$log_file" 2>&1 &
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

# Start Camera Server
start_camera_server() {
    # Extract Camera port from environment
    local camera_port=$(extract_port "$VITE_CAMERA_URL")
    camera_port=${camera_port:-8001}

    print_status "🚀 Starting Camera Server on port $camera_port..."

    # Check if systemd service is available and running
    if systemctl is-active --quiet coordinate-camera 2>/dev/null; then
        print_status "✅ Camera Server is already running as systemd service"
        return 0
    elif systemctl list-unit-files | grep -q coordinate-camera 2>/dev/null; then
        print_status "🔄 Starting Camera Server via systemd..."
        if sudo systemctl start coordinate-camera; then
            print_status "✅ Camera Server started via systemd"
            return 0
        else
            print_warning "Failed to start via systemd, falling back to direct execution"
        fi
    fi

    # Fallback to direct execution
    # Clean up any existing processes on the Camera port
    cleanup_port "$camera_port" "Camera Server"

    # Start Camera Server
    start_service "Camera Server" \
        "python camera_service.py" \
        "${PROJECT_ROOT}/camera" \
        "$camera_port"

    return $?
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    start_camera_server
fi
