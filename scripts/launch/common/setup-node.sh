#!/bin/bash

# Node.js Environment Setup
# Extracted from start-dev.sh for modular architecture

set -e

# Configuration constants
# Install timeout in seconds (default: 12 minutes for Node.js dependencies)
INSTALL_TIMEOUT=${INSTALL_TIMEOUT:-720}

# Source environment loader if not already loaded
if [ -z "$PROJECT_ROOT" ]; then
    source "$(dirname "${BASH_SOURCE[0]}")/load-env.sh"
fi

# Set up Node.js cache directories from .env.common
export NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-${HOME}/.cache/npm}"
export YARN_CACHE_FOLDER="${YARN_CACHE_FOLDER:-${HOME}/.cache/yarn}"
export PNPM_HOME="${PNPM_HOME:-${HOME}/.cache/pnpm}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[NODE]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[NODE]${NC} $1"
}

print_error() {
    echo -e "${RED}[NODE]${NC} $1"
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
        echo -e "\n${YELLOW}[NODE]${NC} ⚠️ Operation timed out after ${timeout}s, terminating..."
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

# Setup Node.js environment for UI Server
setup_node_env() {
    local ui_dir="${PROJECT_ROOT}/ui"

    print_status "🔧 Setting up UI Server dependencies..."

    if [ ! -d "$ui_dir" ]; then
        print_error "❌ UI directory not found: $ui_dir"
        return 1
    fi

    cd "$ui_dir"

    # Check if node_modules exists and package.json is newer
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ]; then
        if [ "${SKIP_DEPENDENCY_INSTALL:-false}" = "true" ]; then
            print_status "⚡ Skipping npm dependency installation (SKIP_DEPENDENCY_INSTALL=true)"
        else
            print_status "📦 Installing npm dependencies..."
            print_status "💡 This may take several minutes. Use --skip-install to skip if dependencies are already installed."

            # Create cache directory and npm install with locking and timeout
            mkdir -p /tmp/coordinate-recorder-locks
            (
                flock -x 200
                mkdir -p "$NPM_CONFIG_CACHE"

                # Try npm install with timeout and progress
                local npm_cmd="npm install --silent --no-audit --no-fund --cache='$NPM_CONFIG_CACHE'"
                if run_with_timeout "$npm_cmd" "Installing npm dependencies" $INSTALL_TIMEOUT; then
                    print_status "✅ npm dependencies installed successfully"
                else
                    print_warning "⚠️ npm install failed or timed out, trying with --legacy-peer-deps..."
                    local npm_legacy_cmd="npm install --legacy-peer-deps --silent --no-audit --no-fund --cache='$NPM_CONFIG_CACHE'"
                    if run_with_timeout "$npm_legacy_cmd" "Installing npm dependencies (legacy mode)" $INSTALL_TIMEOUT; then
                        print_status "✅ npm dependencies installed successfully (legacy mode)"
                    else
                        print_error "❌ Failed to install npm dependencies after timeout"
                        cd "$PROJECT_ROOT"
                        return 1
                    fi
                fi
            ) 200>/tmp/coordinate-recorder-locks/npm-cache.lock
        fi
    else
        print_status "✅ npm dependencies already up to date"
    fi

    # Verify vite is available
    if ! npx vite --version >/dev/null 2>&1; then
        print_error "❌ Vite is not available after npm install"
        cd "$PROJECT_ROOT"
        return 1
    fi

    print_status "✅ UI Server environment ready"
    cd "$PROJECT_ROOT"
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    setup_node_env
fi
