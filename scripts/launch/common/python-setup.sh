#!/bin/bash

# Python Environment Setup
# Extracted from start-dev.sh for modular architecture

set -e

# Configuration constants
# Install timeout in seconds (default: 20 minutes for heavy ML dependencies)
INSTALL_TIMEOUT=${INSTALL_TIMEOUT:-1200}

# Source environment loader if not already loaded
if [ -z "$PROJECT_ROOT" ]; then
    source "$(dirname "${BASH_SOURCE[0]}")/load-env.sh"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[PYTHON]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[PYTHON]${NC} $1"
}

print_error() {
    echo -e "${RED}[PYTHON]${NC} $1"
}

# Function to display progress with dots
show_progress() {
    local pid=$1
    local message=$2
    local timeout=${3:-$INSTALL_TIMEOUT}
    local elapsed=0
    local interval=2

    echo -n "$message"

    while kill -0 $pid 2>/dev/null && [ $elapsed -lt $timeout ]; do
        echo -n "."
        sleep $interval
        elapsed=$((elapsed + interval))

        # Show elapsed time every 30 seconds
        if [ $((elapsed % 30)) -eq 0 ]; then
            echo -n " (${elapsed}s)"
        fi
    done

    # Check if process timed out
    if kill -0 $pid 2>/dev/null; then
        echo -e "\n${YELLOW}[PYTHON]${NC} ⚠️ Operation timed out after ${timeout}s, terminating..."
        kill -TERM $pid 2>/dev/null || true
        sleep 2
        kill -KILL $pid 2>/dev/null || true
        return 1
    fi

    echo -e " ✅ (${elapsed}s)"
    return 0
}

# Function to run command with timeout and progress display
run_with_timeout() {
    local command="$1"
    local message="$2"
    local timeout=${3:-$INSTALL_TIMEOUT}

    # Run command in background
    bash -c "$command" &
    local pid=$!

    # Show progress
    if show_progress $pid "$message" $timeout; then
        wait $pid
        return $?
    else
        return 1
    fi
}

# Function to check if running in production environment
is_production_environment() {
    if [[ "$PROJECT_ROOT" == "/home/pi/coordinate-recorder" ]] || [[ $(hostname) == *"pi-camera"* ]] || [[ "$USER" == "pi" && -d "/home/pi" ]]; then
        return 0  # true
    else
        return 1  # false
    fi
}

# 本番 VPS / CI は 3.12。venv はここの python3 で作られるため、ローカルが 3.11 のままだと
# 「ローカルで通ったのに CI で落ちる」が起きる。Pi は bookworm のシステム
# Python 3.11.2 で動かすのが正しく、上げようがない警告になるので本番環境では黙る。
warn_if_python_below_312() {
    if is_production_environment; then
        return 0
    fi

    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        print_warning "⚠️ python3 is $(python3 --version 2>&1); production VPS / CI use 3.12"
        print_warning "   Align local development with 3.12 (only the Pi camera stays on 3.11)"
    fi
}

# Function to check and install Python dependencies
setup_python_env() {
    local name=$1
    local directory=$2
    local requirements_file=$3

    print_status "🔧 Setting up Python environment for $name..."

    cd "$directory"

    # Detect environment and set up appropriate shared directories
    local cache_base_dir
    local venv_base_dir

    # Detect environment and set up directories
    if [ -d "${PROJECT_ROOT}/.git" ]; then
        # Main repository
        cache_base_dir="${PROJECT_ROOT}/.cache"
        venv_base_dir="${PROJECT_ROOT}/.venvs"
    elif is_production_environment; then
        # Raspberry Pi production server: use shared venv structure
        cache_base_dir="/home/pi/.coordinate-recorder-cache"
        venv_base_dir="/home/pi/.coordinate-recorder-venvs"
    elif [[ "$PROJECT_ROOT" == *"/coordinate-recorder" ]]; then
        # Other coordinate-recorder directories (local integration test)
        cache_base_dir="${HOME}/.coordinate-recorder-cache"
        venv_base_dir="${HOME}/.coordinate-recorder-venvs"
    else
        # Generic standalone directory
        cache_base_dir="${HOME}/.coordinate-recorder-cache"
        venv_base_dir="${HOME}/.coordinate-recorder-venvs"
    fi

    # Set up shared cache directories and virtual environments
    # Use environment variables from .env.common if already set, otherwise fall back to computed paths
    export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${cache_base_dir}/pip}"
    export YOLO_CACHE_DIR="${YOLO_CACHE_DIR:-${cache_base_dir}/yolo}"
    export VENV_CACHE_DIR="${VENV_CACHE_DIR:-${venv_base_dir}}"
    export POETRY_CACHE_DIR="${POETRY_CACHE_DIR:-${cache_base_dir}/poetry}"

    # Create directories with proper locking to avoid race conditions
    mkdir -p /tmp/coordinate-recorder-locks
    (
        flock -x 200
        mkdir -p "$PIP_CACHE_DIR" "$YOLO_CACHE_DIR" "$VENV_CACHE_DIR" "$POETRY_CACHE_DIR"
    ) 200>/tmp/coordinate-recorder-locks/cache-dirs.lock

    # Debug: Show environment detection and cache directories
    local env_type="Unknown"
    if [ -d "${PROJECT_ROOT}/.git" ]; then
        env_type="Repository"
    elif is_production_environment; then
        env_type="Raspberry Pi Production"
    elif [[ "$PROJECT_ROOT" == *"/coordinate-recorder" ]]; then
        env_type="Local Integration Test"
    else
        env_type="Standalone"
    fi

    print_status "🌍 Environment: $env_type"
    print_status "📁 Cache directories:"
    print_status "  PIP: $PIP_CACHE_DIR"
    print_status "  VENV: $VENV_CACHE_DIR"
    print_status "  POETRY: $POETRY_CACHE_DIR"

    # Configure Poetry to use shared cache
    export POETRY_CACHE_DIR="$POETRY_CACHE_DIR"
    export POETRY_VENV_PATH="$VENV_CACHE_DIR"

    # Use shared virtual environment based on requirements hash
    local requirements_hash=""
    if [ -f "$requirements_file" ]; then
        requirements_hash=$(md5 -q "$requirements_file" 2>/dev/null || echo "default")
    else
        requirements_hash="default"
    fi

    local shared_venv_path="${VENV_CACHE_DIR}/$(echo ${name} | tr '[:upper:]' '[:lower:]' | tr ' ' '-')-${requirements_hash}"

    # Create or use existing shared virtual environment with locking
    local venv_lock_file="/tmp/coordinate-recorder-locks/venv-$(echo ${name} | tr '[:upper:]' '[:lower:]' | tr ' ' '-')-${requirements_hash:0:8}.lock"
    (
        flock -x 200
        if [ ! -d "$shared_venv_path" ]; then
            print_status "Creating shared virtual environment for $name (hash: ${requirements_hash:0:8})..."
            python3 -m venv "$shared_venv_path"

            # Create symlink for backward compatibility
            # Remove existing venv link/directory first (especially important for production deployments)
            if [ -L "venv" ] || [ -d "venv" ]; then
                rm -rf venv 2>/dev/null || true
            fi
            ln -sf "$shared_venv_path" venv
        else
            print_status "Using existing shared virtual environment for $name..."
            # Check if the virtual environment is corrupted
            if ! "$shared_venv_path/bin/python" -c "import sys; print('OK')" >/dev/null 2>&1; then
                print_warning "⚠️ Virtual environment appears corrupted, recreating..."
                rm -rf "$shared_venv_path"
                python3 -m venv "$shared_venv_path"
            fi

            # Ensure symlink exists and points to correct location (force recreate for production)
            # Force recreate symlink in production, or create if missing in development
            if is_production_environment || [ ! -L "venv" ]; then
                rm -rf venv 2>/dev/null || true
                ln -sf "$shared_venv_path" venv
                if is_production_environment; then
                    print_status "🔧 Production environment detected - symlink forcibly recreated"
                fi
            fi
        fi
    ) 200>"$venv_lock_file"

    # Mark this generation as used. scripts/maintenance/prune-stale-venvs.sh reads the
    # directory mtime as "last used", and nothing else ever moves it: writes land in
    # site-packages, not in the directory itself, so without this touch a generation in
    # daily use looks exactly as old as an abandoned one.
    touch "$shared_venv_path" 2>/dev/null || true

    # Activate shared virtual environment
    source "$shared_venv_path/bin/activate"

    # Upgrade pip with shared cache
    pip install --upgrade pip --cache-dir "$PIP_CACHE_DIR" > /dev/null 2>&1

    # Install requirements if file exists (skip if SKIP_DEPENDENCY_INSTALL is set)
    if [ -f "$requirements_file" ]; then
        if [ "${SKIP_DEPENDENCY_INSTALL:-false}" = "true" ]; then
            print_status "⚡ Skipping dependency installation (SKIP_DEPENDENCY_INSTALL=true)"
        else
            print_status "Installing dependencies for $name..."
            print_status "💡 This may take several minutes. Use --skip-install to skip if dependencies are already installed."

            # Try to install all dependencies with timeout and progress
            local pip_cmd="pip install -r '$requirements_file' --cache-dir '$PIP_CACHE_DIR' --no-warn-script-location --disable-pip-version-check"
            if run_with_timeout "$pip_cmd" "Installing dependencies from $requirements_file"; then
                print_status "✅ All dependencies installed successfully"
            else
                print_warning "⚠️ Full installation failed or timed out, trying critical packages individually..."

                # Install critical packages individually with shorter timeouts
                local critical_packages=("fastapi>=0.104" "uvicorn>=0.24" "sqlalchemy>=2.0" "psycopg2-binary" "alembic>=1.12")
                for package in "${critical_packages[@]}"; do
                    local critical_cmd="pip install '$package' --cache-dir '$PIP_CACHE_DIR' --no-warn-script-location --disable-pip-version-check"
                    if run_with_timeout "$critical_cmd" "Installing critical: $package" 120; then
                        print_status "✅ Installed: $package"
                    else
                        print_warning "⚠️ Failed to install: $package (continuing...)"
                    fi
                done

                # Optional packages with even shorter timeouts
                local optional_packages=("opencv-python-headless" "ultralytics" "scikit-learn")
                for package in "${optional_packages[@]}"; do
                    local optional_cmd="pip install '$package' --cache-dir '$PIP_CACHE_DIR' --no-warn-script-location --disable-pip-version-check"
                    if run_with_timeout "$optional_cmd" "Installing optional: $package" 180; then
                        print_status "✅ Installed: $package"
                    else
                        print_warning "⚠️ Skipped optional: $package (timeout/error)"
                    fi
                done
            fi
        fi
    else
        print_warning "No requirements file found at $requirements_file"
    fi

    # Install additional dependencies based on service (skip if SKIP_DEPENDENCY_INSTALL is set)
    if [ "${SKIP_DEPENDENCY_INSTALL:-false}" != "true" ]; then
        if [[ "$name" == "Camera"* ]]; then
            # Camera service specific dependencies with timeout
            print_status "Installing camera service dependencies..."
            local camera_cmd="pip install httpx fastapi uvicorn --no-warn-script-location --disable-pip-version-check --cache-dir '$PIP_CACHE_DIR'"
            run_with_timeout "$camera_cmd" "Installing camera core packages" 120 || print_warning "⚠️ Some camera dependencies failed"

            # opencv-python is optional for basic camera functionality
            local opencv_cmd="pip install opencv-python --no-warn-script-location --disable-pip-version-check --cache-dir '$PIP_CACHE_DIR'"
            run_with_timeout "$opencv_cmd" "Installing OpenCV (optional)" 180 || print_warning "⚠️ OpenCV installation skipped"
        elif [[ "$name" == "API"* ]]; then
            # API service specific dependencies with timeout
            print_status "Installing API service core dependencies..."
            local api_cmd="pip install sqlalchemy fastapi uvicorn --no-warn-script-location --disable-pip-version-check --cache-dir '$PIP_CACHE_DIR'"
            run_with_timeout "$api_cmd" "Installing API core packages" 120 || print_warning "⚠️ Some API dependencies failed"

            # Optional ML dependencies with timeout
            print_status "Installing optional ML dependencies..."
            local ml_cmd="pip install scikit-learn --no-warn-script-location --disable-pip-version-check --cache-dir '$PIP_CACHE_DIR'"
            run_with_timeout "$ml_cmd" "Installing ML packages (optional)" 180 || print_warning "⚠️ scikit-learn installation skipped"
        fi
    fi

    # Deactivate virtual environment (will be reactivated when service starts)
    deactivate

    print_status "✅ $name Python environment ready"
}

# Setup both API and Camera environments
setup_all_python_envs() {
    print_status "🔧 Setting up all Python environments..."
    warn_if_python_below_312
    setup_python_env "API Server" "${PROJECT_ROOT}/api" "${PROJECT_ROOT}/requirements-api.txt"
    setup_python_env "Camera Server" "${PROJECT_ROOT}/camera" "${PROJECT_ROOT}/camera/requirements.txt"
    print_status "✅ All Python environments ready"
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    setup_all_python_envs
fi
