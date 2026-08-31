#!/bin/bash

# CLAUDE.md Modular Startup Script with Memory Optimization
# Unified startup with automatic memory optimization for Raspberry Pi

############################################################
# 警告: このスクリプトは将来的に廃止予定です
#
# systemd への移行を推奨します：
#   - 本番環境: sudo systemctl start coordinate-*.service
#   - 開発環境: systemd/scripts/start-services.sh
#
# 詳細: scripts/dev/README.md
############################################################

echo "⚠️  警告: このスクリプトは廃止予定です。systemd の使用を推奨します。" >&2
echo ""

# systemd サービスが実行中か確認（Linux のみ）
if [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl &> /dev/null; then
    if systemctl is-active --quiet coordinate-camera.service || \
       systemctl is-active --quiet coordinate-api.service || \
       systemctl is-active --quiet coordinate-ui.service; then
        echo "❌ systemd サービスが実行中です。競合を避けるため終了します。" >&2
        echo "   systemd サービスを使用するか、以下で停止してください：" >&2
        echo "   sudo systemctl stop coordinate-*.service" >&2
        exit 1
    fi
fi

set -e

# Parse command line arguments
UI_FAST_MODE=false
SKIP_CAMERA=false
MEMORY_OPTIMIZED=false
SKIP_INSTALL=false
BACKGROUND_INSTALL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --fast|--ui-fast)
            UI_FAST_MODE=true
            shift
            ;;
        --skip-camera|--no-camera)
            SKIP_CAMERA=true
            shift
            ;;
        --memory-optimized|--lightweight)
            MEMORY_OPTIMIZED=true
            shift
            ;;
        --skip-install|--no-install)
            SKIP_INSTALL=true
            shift
            ;;
        --background-install|--async-install)
            BACKGROUND_INSTALL=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --fast, --ui-fast       Enable fast UI mode (minimized TypeScript checks)"
            echo "  --skip-camera, --no-camera  Skip camera service startup"
            echo "  --memory-optimized, --lightweight  Enable memory optimizations"
            echo "  --skip-install, --no-install  Skip dependency installation"
            echo "  --background-install, --async-install  Install dependencies in background"
            echo "  --help, -h              Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Auto-detect memory optimization need
if [ "$MEMORY_OPTIMIZED" = false ]; then
    # Check if we're on Raspberry Pi or low memory system
    if [[ $(hostname) == *"pi-camera"* ]] || [ -f /proc/meminfo ]; then
        if [ -f /proc/meminfo ]; then
            available_mb=$(grep MemAvailable /proc/meminfo | awk '{print int($2/1024)}' 2>/dev/null || echo "999999")
            if [ "$available_mb" -lt 2000 ]; then
                echo "🧠 Low memory detected (${available_mb}MB), enabling memory optimizations"
                MEMORY_OPTIMIZED=true
            fi
        fi
    fi
fi

# Export options for child scripts
export UI_FAST_MODE
export SKIP_CAMERA
export MEMORY_OPTIMIZED

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[COORDINATOR]${NC} $1"
}

# Set environment variables for dependency installation control
if [ "$SKIP_INSTALL" = true ]; then
    export SKIP_DEPENDENCY_INSTALL=true
    print_status "⚡ Dependency installation will be skipped"
fi

if [ "$BACKGROUND_INSTALL" = true ]; then
    export BACKGROUND_DEPENDENCY_INSTALL=true
    print_status "🔄 Dependencies will be installed in background"
fi

# Configuration constants
readonly SERVICE_INIT_WAIT=5

print_warning() {
    echo -e "${YELLOW}[COORDINATOR]${NC} $1"
}

print_error() {
    echo -e "${RED}[COORDINATOR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[COORDINATOR]${NC} $1"
}

# Check virtual environment for production deployments
check_virtual_environment() {
    print_status "🐍 Checking virtual environment..."

    local venv_dir="${PROJECT_ROOT}/venv"

    # Check if we're in externally managed Python environment
    if python3 -m pip --version 2>&1 | grep -q "externally-managed-environment"; then
        print_warning "⚠️ Externally managed Python environment detected"

        # Check if virtual environment exists
        if [ ! -d "$venv_dir" ]; then
            print_error "❌ Virtual environment not found at: $venv_dir"
            print_status "💡 Please run the deployment script first:"
            print_status "   ./scripts/deploy-production.sh"
            exit 1
        fi

        # Check if virtual environment is activated
        if [ -z "$VIRTUAL_ENV" ]; then
            print_status "🔄 Activating virtual environment..."
            source "$venv_dir/bin/activate"
            print_status "✅ Virtual environment activated: $VIRTUAL_ENV"
        else
            print_status "✅ Virtual environment already active: $VIRTUAL_ENV"
        fi
    else
        print_status "✅ Standard Python environment detected"
    fi
}

# Auto-detect project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PROJECT_ROOT

print_header "🚀 Starting Coordinate Recorder Development Environment (Modular)"
print_status "Project root: $PROJECT_ROOT"

# Display memory optimization status
if [ "$MEMORY_OPTIMIZED" = true ]; then
    print_status "🧠 Memory optimizations: ENABLED (from .env.common)"
    print_status "💡 All features available with memory-efficient settings"
else
    print_status "🔧 Running in standard mode"
fi

# Script paths
ENV_LOADER="${PROJECT_ROOT}/scripts/launch/common/load-env.sh"
PYTHON_SETUP="${PROJECT_ROOT}/scripts/launch/common/python-setup.sh"
NODE_SETUP="${PROJECT_ROOT}/scripts/launch/common/setup-node.sh"
HEALTH_CHECK="${PROJECT_ROOT}/scripts/health-check.sh"
PORT_CLEANUP="${PROJECT_ROOT}/scripts/launch/common/port-cleanup.sh"
WAIT_FOR_SERVICE="${PROJECT_ROOT}/scripts/launch/common/wait-service.sh"

DB_START="${PROJECT_ROOT}/scripts/launch/services/start-db.sh"
API_START="${PROJECT_ROOT}/scripts/launch/services/start-api.sh"
CAMERA_START="${PROJECT_ROOT}/scripts/launch/services/start-camera.sh"
UI_START="${PROJECT_ROOT}/scripts/launch/services/start-ui.sh"
BROWSER_START="${PROJECT_ROOT}/scripts/launch/services/start-browser.sh"

# Verify all required scripts exist
check_scripts() {
    local missing_scripts=()

    for script in "$ENV_LOADER" "$PYTHON_SETUP" "$NODE_SETUP" "$HEALTH_CHECK" "$PORT_CLEANUP" "$WAIT_FOR_SERVICE" "$DB_START" "$API_START" "$CAMERA_START" "$UI_START" "$BROWSER_START"; do
        if [ ! -f "$script" ]; then
            missing_scripts+=("$script")
        fi
    done

    if [ ${#missing_scripts[@]} -gt 0 ]; then
        print_error "❌ Missing required scripts:"
        for script in "${missing_scripts[@]}"; do
            print_error "  - $script"
        done
        print_error "Please ensure all modular scripts are in place."
        exit 1
    fi

    print_status "✅ All required scripts found"
}

# Check scripts are executable (permissions should be set by git hooks)
check_scripts_executable() {
    print_status "🔧 Checking script permissions..."
    local missing_perms=()

    for script in "$ENV_LOADER" "$PYTHON_SETUP" "$NODE_SETUP" "$HEALTH_CHECK" "$PORT_CLEANUP" "$WAIT_FOR_SERVICE" "$DB_START" "$API_START" "$CAMERA_START" "$UI_START" "$BROWSER_START"; do
        if [ ! -x "$script" ]; then
            missing_perms+=("$script")
        fi
    done

    if [ ${#missing_perms[@]} -gt 0 ]; then
        print_warning "⚠️ Scripts missing execute permissions:"
        for script in "${missing_perms[@]}"; do
            print_warning "  - $script"
        done
        print_status "Setting execute permissions as fallback..."
        chmod +x "$ENV_LOADER" "$PYTHON_SETUP" "$NODE_SETUP" "$HEALTH_CHECK" "$PORT_CLEANUP" "$WAIT_FOR_SERVICE"
        chmod +x "$DB_START" "$API_START" "$CAMERA_START" "$UI_START" "$BROWSER_START"
    fi

    print_status "✅ Script permissions verified"
}

# Initialize process manager
init_process_manager() {
    local process_manager="${PROJECT_ROOT}/scripts/process-manager.sh"
    local pids_file="${PROJECT_ROOT}/.dev-pids"

    if [ -f "$process_manager" ]; then
        print_status "🔧 Initializing process manager..."
        "$process_manager" init
        "$process_manager" cleanup
        print_status "✅ Process manager initialized"
    else
        print_warning "⚠️ Process manager not found, using legacy PID management"
        echo "" > "$pids_file"
    fi
}

# Fix Playwright Chrome profile conflicts (Claude Code specific issue)
fix_playwright_conflicts() {
    print_status "🎭 Resolving Playwright Chrome profile conflicts..."

    # Clean up Chrome profile cache that causes conflicts between Claude Code sessions
    local chrome_profile_dir="$HOME/Library/Caches/ms-playwright/mcp-chrome-profile"
    if [ -d "$chrome_profile_dir" ]; then
        print_status "🧹 Cleaning Chrome profile cache: $chrome_profile_dir"
        rm -rf "$chrome_profile_dir" 2>/dev/null || true
        print_status "✅ Chrome profile cache cleaned"
    fi

    # Clean up any stale Playwright processes
    local playwright_pids=$(pgrep -f "mcp-server-playwright" 2>/dev/null || true)
    if [ -n "$playwright_pids" ]; then
        print_warning "🔄 Found stale Playwright processes: $playwright_pids"
        echo "$playwright_pids" | xargs kill -TERM 2>/dev/null || true
        sleep 2
        # Force kill if still running
        remaining_pids=$(pgrep -f "mcp-server-playwright" 2>/dev/null || true)
        if [ -n "$remaining_pids" ]; then
            echo "$remaining_pids" | xargs kill -KILL 2>/dev/null || true
        fi
        print_status "✅ Playwright processes cleaned up"
    fi

    print_status "✅ Playwright conflicts resolved"
}


# Step 1: Load environment configuration
load_environment() {
    print_header "📋 Step 1: Loading Environment Configuration"
    source "$ENV_LOADER"
    load_environment
    setup_directories
    configure_urls
    print_status "✅ Environment configuration loaded"
}

# Step 2: Setup development environments (parallel with resource locking)
setup_environments() {
    print_header "🔧 Step 2: Setting up Development Environments (Parallel)"

    # Check for virtual environment in production (Raspberry Pi)
    if [[ $(hostname) == *"pi-camera"* ]] || [ -n "$FORCE_VENV" ]; then
        check_virtual_environment
    fi

    if [ "$SKIP_INSTALL" = true ]; then
        print_status "⚡ Skipping environment setup (--skip-install flag used)"
        print_status "✅ All development environments ready (skipped)"
        return 0
    fi

    # Create lock directory if it doesn't exist
    mkdir -p /tmp/coordinate-recorder-locks

    if [ "$BACKGROUND_INSTALL" = true ]; then
        print_status "🔄 Starting dependency installation in background..."

        # Start installations in background and continue
        (
            print_status "🐍 Starting Python environment setup in background..."
            (flock -x 200; "$PYTHON_SETUP") 200>/tmp/coordinate-recorder-locks/pip-cache.lock && \
            print_status "✅ Background Python environment setup completed" || \
            print_warning "⚠️ Background Python environment setup failed"
        ) &

        (
            print_status "🌐 Starting Node.js environment setup in background..."
            "$NODE_SETUP" && \
            print_status "✅ Background Node.js environment setup completed" || \
            print_warning "⚠️ Background Node.js environment setup failed"
        ) &

        print_status "✅ Background installations started, continuing with service startup..."
    else
        # Start Python and Node.js setup in parallel with resource locking
        # Python setup with pip cache lock
        (flock -x 200; "$PYTHON_SETUP") 200>/tmp/coordinate-recorder-locks/pip-cache.lock &
        local python_pid=$!

        # Node.js setup (no shared resources, can run freely)
        "$NODE_SETUP" &
        local node_pid=$!

        # Wait for both to complete
        print_status "⏳ Waiting for environment setup to complete..."
        local setup_failed=false

        if wait $python_pid; then
            print_status "✅ Python environment setup completed"
        else
            print_error "❌ Python environment setup failed"
            setup_failed=true
        fi

        if wait $node_pid; then
            print_status "✅ Node.js environment setup completed"
        else
            print_error "❌ Node.js environment setup failed"
            setup_failed=true
        fi

        if [ "$setup_failed" = true ]; then
            print_warning "⚠️ Some environment setups failed, but continuing..."
            print_status "💡 You can retry with: ./scripts/start-development.sh (to reinstall dependencies)"
        fi

        print_status "✅ Development environment setup phase completed"
    fi
}

# Step 3: Start database service
start_database() {
    print_header "🗄️ Step 3: Starting Database Service"
    if "$DB_START"; then
        print_status "✅ Database service ready"
    else
        print_error "❌ Database service failed to start"
        return 1
    fi
}

# Step 4: Start application services (parallel)
start_services() {
    print_header "🚀 Step 4: Starting Application Services (Parallel)"

    # Start all services in parallel
    "$API_START" &
    local api_pid=$!

    local camera_pid=""
    if [ "$SKIP_CAMERA" = "false" ]; then
        "$CAMERA_START" &
        camera_pid=$!
    else
        print_status "⏭️ Skipping camera service (--skip-camera flag used)"
        print_warning "⚠️ カメラ依存機能（撮影・ストリーミング）が無効化されています"
        print_status "📸 カメラ機能が必要な場合は --skip-camera オプションを外してください"
    fi


    "$UI_START" &
    local ui_pid=$!

    # Wait for all services to start
    print_status "⏳ Waiting for services to start..."
    local failed_services=()

    if wait $api_pid; then
        print_status "✅ API service started successfully"
    else
        print_error "❌ API service failed to start"
        failed_services+=("API")
    fi

    if [ "$SKIP_CAMERA" = "false" ] && [ -n "$camera_pid" ]; then
        if wait $camera_pid; then
            print_status "✅ Camera service started successfully"
        else
            print_error "❌ Camera service failed to start"
            failed_services+=("Camera")
        fi
    fi


    if wait $ui_pid; then
        print_status "✅ UI service started successfully"
    else
        print_error "❌ UI service failed to start"
        failed_services+=("UI")
    fi

    if [ ${#failed_services[@]} -gt 0 ]; then
        print_error "❌ Some services failed to start: ${failed_services[*]}"
        print_status "Check individual service logs in ${PROJECT_ROOT}/logs/"
        return 1
    fi

    if [ "$SKIP_CAMERA" = "true" ]; then
        print_status "✅ Selected application services started (camera skipped)"
    else
        print_status "✅ All application services started"
    fi
}

# Step 5: Wait for services to initialize
wait_for_initialization() {
    print_header "⏳ Step 5: Waiting for Service Initialization"

    # Use intelligent service readiness checking instead of fixed wait
    if "$WAIT_FOR_SERVICE" core 45; then
        print_status "✅ Core services are ready and responding"
    else
        print_warning "⚠️ Some services may not be fully ready, but continuing..."
        print_status "Falling back to ${SERVICE_INIT_WAIT}s wait period..."
        sleep $SERVICE_INIT_WAIT
    fi

    print_status "✅ Service initialization completed"
}

# Step 6: Perform health checks
perform_health_checks() {
    print_header "🏥 Step 6: Performing Health Checks"

    # Use new comprehensive health check
    if "$WAIT_FOR_SERVICE" health; then
        print_status "✅ Comprehensive health checks passed"
    elif "$HEALTH_CHECK"; then
        print_status "✅ Legacy health checks completed successfully"
    else
        print_warning "⚠️ Some health checks failed, but services may still be functional"
        print_status "Check individual service logs in ${PROJECT_ROOT}/logs/"
    fi
}

# Step 7: Start browser for Raspberry Pi
start_browser_if_needed() {
    print_header "🌐 Step 7: Browser Initialization"

    # Check if we're on Raspberry Pi and should start kiosk browser
    if [[ $(hostname) == *"pi-camera"* ]]; then
        print_status "🍓 Raspberry Pi detected, starting kiosk browser..."
        if "$BROWSER_START" auto; then
            print_status "✅ Touchscreen interface ready"
        else
            print_warning "⚠️ Browser startup failed, manual launch may be needed"
        fi
    else
        print_status "💻 Regular development environment, browser startup skipped"
        print_status "💡 Access UI at: http://localhost:${UI_PORT:-3000}"
    fi
}

# Display final status
display_final_status() {
    print_header "🎉 Coordinate Recorder Development Environment Started!"
    print_status ""
    print_status "🔄 Services are now running persistently in the background"
    print_status "📝 Service PIDs saved to: ${PROJECT_ROOT}/.dev-pids"
    print_status "📁 Service logs saved to: ${PROJECT_ROOT}/logs/"

    # Show UI mode status
    if [ "$UI_FAST_MODE" = "true" ]; then
        print_status "⚡ UI Fast Mode: ENABLED (TypeScript checks minimized)"
    else
        print_status "🐌 UI Standard Mode: ENABLED (full TypeScript checks)"
    fi

    if [ "$SKIP_INSTALL" = "true" ]; then
        print_status "⚡ Dependency Installation: SKIPPED"
    elif [ "$BACKGROUND_INSTALL" = "true" ]; then
        print_status "🔄 Dependency Installation: BACKGROUND MODE"
        print_status "💡 Dependencies are installing in background, check logs for progress"
    else
        print_status "📦 Dependency Installation: COMPLETED"
    fi

    print_status ""
    print_status "🛑 To stop all services, run: ./scripts/stop-development.sh"
    print_status "🔍 To monitor services, run: ./scripts/debug/check-ports.sh"
    print_status ""
    print_status "💡 Launch options:"
    print_status "  - Fast UI:         ./scripts/start-development.sh --fast"
    print_status "  - Skip camera:     ./scripts/start-development.sh --skip-camera"
    print_status "  - Skip install:    ./scripts/start-development.sh --skip-install"
    print_status "  - Background install: ./scripts/start-development.sh --background-install"
    print_status "  - Memory optimized: ./scripts/start-development.sh --memory-optimized"
    print_status "  - Standard:        ./scripts/start-development.sh"
    print_status ""
    print_status "💡 Individual service management:"
    print_status "  - Database: ./scripts/launch/services/start-db.sh"
    print_status "  - API:      ./scripts/launch/services/start-api.sh"
    print_status "  - Camera:   ./scripts/launch/services/start-camera.sh"
    print_status "  - UI:       ./scripts/launch/services/start-ui.sh"
    print_status "  - Browser:  ./scripts/launch/services/start-browser.sh"
    print_status ""
    print_status "🔧 Utility scripts:"
    print_status "  - Port cleanup:    ./scripts/launch/common/port-cleanup.sh cleanup"
    print_status "  - Service wait:    ./scripts/launch/common/wait-service.sh all"
    print_status "  - Health check:    ./scripts/launch/common/wait-service.sh health"
}

# Main execution flow
main() {
    # Pre-flight checks
    check_scripts
    check_scripts_executable
    init_process_manager
    fix_playwright_conflicts

    # Clean up port conflicts before starting services
    print_header "🧹 Cleaning Up Port Conflicts"
    "$PORT_CLEANUP" cleanup

    # Execute startup sequence
    load_environment
    setup_environments
    start_database
    start_services
    wait_for_initialization
    perform_health_checks
    start_browser_if_needed
    display_final_status

    print_header "✨ Startup sequence completed successfully!"
}

# Error handling
trap 'print_error "❌ Startup sequence interrupted"; exit 1' INT TERM

# Execute main function
main "$@"
