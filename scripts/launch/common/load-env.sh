#!/bin/bash

# Environment Variables Loader
# Extracted from start-dev.sh for modular architecture

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[ENV]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[ENV]${NC} $1"
}

print_error() {
    echo -e "${RED}[ENV]${NC} $1"
}

# Auto-detect project root
if [ -z "$PROJECT_ROOT" ]; then
    PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
    export PROJECT_ROOT
fi

print_status "Project root: $PROJECT_ROOT"

# === タイムアウト設定 ===
# Default timeout settings for installation processes
export INSTALL_TIMEOUT=${INSTALL_TIMEOUT:-600}  # 10 minutes for Python packages
export NPM_INSTALL_TIMEOUT=${NPM_INSTALL_TIMEOUT:-480}  # 8 minutes for npm packages
print_status "⏱️ Install timeouts: Python=${INSTALL_TIMEOUT}s, Node.js=${NPM_INSTALL_TIMEOUT}s"

# === 環境変数統合システム ===
# Load environment variables from .env.common and .env (new system)
load_environment() {
    local loaded_common=false
    local loaded_session=false

    # Load common environment variables first
    if [ -f "$PROJECT_ROOT/.env.common" ]; then
        print_status "📄 Loading .env.common..."
        # セキュリティ: 必要な変数のみを個別にエクスポート
        while IFS='=' read -r key value; do
            # コメント行と空行をスキップ
            [[ "$key" =~ ^[[:space:]]*# ]] && continue
            [[ -z "$key" ]] && continue

            # 必要な環境変数のみをエクスポート（セキュリティ向上）
            case "$key" in
                API_PORT|UI_PORT|CAMERA_PORT|POSTGRES_PORT|DATABASE_URL|API_URL|VITE_API_URL|VITE_CAMERA_URL|STORAGE_TYPE|PHOTOS_PATH|DATA_PATH|LOGS_PATH|VENV_PATH|SKIP_DEPENDENCY_INSTALL)
                    export "$key=$value"
                    ;;
            esac
        done < "$PROJECT_ROOT/.env.common"
        loaded_common=true
    fi

    # Load session-specific environment variables (higher priority)
    if [ -f "$PROJECT_ROOT/.env" ]; then
        print_status "🔧 Loading .env..."
        # セキュリティ: 必要な変数のみを個別にエクスポート
        while IFS='=' read -r key value; do
            # コメント行と空行をスキップ
            [[ "$key" =~ ^[[:space:]]*# ]] && continue
            [[ -z "$key" ]] && continue

            # 必要な環境変数のみをエクスポート（セキュリティ向上）
            case "$key" in
                API_PORT|UI_PORT|CAMERA_PORT|POSTGRES_PORT|DATABASE_URL|API_URL|VITE_API_URL|VITE_CAMERA_URL|STORAGE_TYPE|PHOTOS_PATH|DATA_PATH|LOGS_PATH|VENV_PATH|SKIP_DEPENDENCY_INSTALL)
                    export "$key=$value"
                    ;;
            esac
        done < "$PROJECT_ROOT/.env"
        loaded_session=true
    fi

    # Fallback to auto-detection if no .env files found
    if [ "$loaded_session" = false ]; then
        print_warning "⚠️  .env file not found. Using auto-detected configuration."
        # Auto-detect session type and configure ports
        auto_detect_environment
    fi

    # Display loaded configuration
    if [ "$loaded_common" = true ] || [ "$loaded_session" = true ]; then
        print_status "✅ Environment loaded successfully!"
        print_status "🔧 Configuration:"
        print_status "   API: ${API_URL:-http://localhost:8000}"
        print_status "   UI: http://localhost:${UI_PORT:-3000}"
        print_status "   Camera: ${VITE_CAMERA_URL:-http://localhost:8001}"
        print_status "   Database: ${DATABASE_URL:-sqlite:///./coordinate_recorder.db}"
    fi
}

# Auto-detect environment for backward compatibility
auto_detect_environment() {
    local current_dir=$(basename "$PROJECT_ROOT")

    if [[ "$current_dir" =~ ^project- ]]; then
        # Project Session: calculate dynamic ports
        print_status "🚀 Detected Project Session: $current_dir"
        local project_hash=$(echo "$current_dir" | md5sum | cut -c1-2)
        local project_offset=$((0x$project_hash % 50 + 10))

        export API_PORT=$((8000 + project_offset))
        export UI_PORT=$((3000 + project_offset))
        export CAMERA_PORT=$((8000 + project_offset + 1))

        export API_URL="http://localhost:$API_PORT"
        export VITE_API_URL="http://localhost:$API_PORT"
        export VITE_CAMERA_URL="http://localhost:$CAMERA_PORT"

        print_status "🎯 Auto-configured ports: API=$API_PORT, UI=$UI_PORT, Camera=$CAMERA_PORT"
    else
        # Manager Session: use default ports
        print_status "🏢 Detected Manager Session"
        export API_PORT=8000
        export UI_PORT=3000
        export CAMERA_PORT=8001

        export API_URL="http://localhost:8000"
        export VITE_API_URL="http://localhost:8000"
        export VITE_CAMERA_URL="http://localhost:8001"
    fi
}

# Setup directories
setup_directories() {
    # Auto-detect and create directories
    export PHOTOS_DIR="${PROJECT_ROOT}/photos"
    export DAILY_TRACKER_DATA_DIR="${PROJECT_ROOT}/api/v2/data"
    export BACKEND_LOG_DIR="${PROJECT_ROOT}/api/v2/logs"

    # Create directories if they don't exist
    mkdir -p "$PHOTOS_DIR"
    mkdir -p "$DAILY_TRACKER_DATA_DIR"
    mkdir -p "$BACKEND_LOG_DIR"

    print_status "📁 Auto-configured directories:"
    print_status "  Photos: $PHOTOS_DIR"
    print_status "  Data: $DAILY_TRACKER_DATA_DIR"
    print_status "  Logs: $BACKEND_LOG_DIR"
}

# Configure environment-based URLs
configure_urls() {
    # Environment-based URL configuration
    if [[ $(hostname) == *"pi-camera"* ]]; then
        export API_URL="http://pi-camera.local:${API_PORT:-8000}"
        export CAMERA_SERVICE_URL="http://pi-camera.local:${CAMERA_PORT:-8001}"
        export VITE_API_URL="http://pi-camera.local:${API_PORT:-8000}"
        export VITE_CAMERA_URL="http://pi-camera.local:${CAMERA_PORT:-8001}"
        print_status "🔧 Raspberry Pi environment detected"
    else
        # Local development - Use .env settings if available, fallback to dynamic ports
        export API_URL="${API_URL:-http://localhost:${API_PORT:-8000}}"
        export CAMERA_SERVICE_URL="${CAMERA_SERVICE_URL:-http://localhost:${CAMERA_PORT:-8001}}"
        export VITE_API_URL="${VITE_API_URL:-http://localhost:${API_PORT:-8000}}"
        export VITE_CAMERA_URL="${VITE_CAMERA_URL:-http://localhost:${CAMERA_PORT:-8001}}"
        print_status "🔧 Local development environment detected"
    fi

    # Configure Python path for coordinate_recorder module imports
    export PYTHONPATH="${PROJECT_ROOT}/src:${PROJECT_ROOT}:${PYTHONPATH}"
    print_status "🐍 Python path configured: ${PROJECT_ROOT}/src"

    print_status "🌐 Environment URLs:"
    print_status "  API: $API_URL"
    print_status "  Camera: $CAMERA_SERVICE_URL"
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    load_environment
    setup_directories
    configure_urls
else
    # Script is being sourced
    print_status "Environment loader ready. Call load_environment() to initialize."
fi
