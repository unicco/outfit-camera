#!/bin/bash

# DEPRECATED: This script will be removed in a future release
# Please use scripts/health-check.sh directly instead
#
# Health Check Functions - Wrapper for unified health-check.sh
# This is now a wrapper that calls the unified health check script
# Maintained for backward compatibility

set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HEALTH_CHECK_SCRIPT="$PROJECT_ROOT/scripts/health-check.sh"

# Check if unified health check script exists
if [ ! -f "$HEALTH_CHECK_SCRIPT" ]; then
    echo "Error: Unified health check script not found at $HEALTH_CHECK_SCRIPT"
    exit 1
fi

# Source environment loader if not already loaded (for backward compatibility)
if [ -z "$PROJECT_ROOT" ]; then
    source "$(dirname "${BASH_SOURCE[0]}")/load-env.sh"
fi

# Legacy function definitions for scripts that might source this file
# These now call the unified health check script

# Colors for output (kept for compatibility)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[HEALTH]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[HEALTH]${NC} $1"
}

print_error() {
    echo -e "${RED}[HEALTH]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[HEALTH]${NC} $1"
}

# Legacy function that now calls the unified script
check_all_services() {
    # Call unified health check in startup mode (lightweight)
    "$HEALTH_CHECK_SCRIPT" --startup --local
}

# Legacy database check function
check_database() {
    "$HEALTH_CHECK_SCRIPT" --module database --local
}

# Legacy port check function (kept for compatibility)
check_port() {
    local port=$1
    if lsof -i :$port > /dev/null 2>&1; then
        return 1  # Port is busy
    else
        return 0  # Port is available
    fi
}

# Legacy extract port function (kept for compatibility)
extract_port() {
    echo "$1" | sed -E 's/.*:([0-9]+).*/\1/'
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    # Call unified health check in startup mode
    print_header "🏥 Running health check (startup mode)..."
    "$HEALTH_CHECK_SCRIPT" --startup --local
fi
