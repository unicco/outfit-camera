#!/bin/bash

# Startup Health Check Script - Lightweight wrapper around health-check.sh
#
# The health checks live in health-check.sh; systemd units still depend on a
# dedicated "startup" mode, so this script keeps that entry point by running
# focused checks via the unified script (#626).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HEALTH_CHECK_SCRIPT="$PROJECT_ROOT/scripts/health-check.sh"

# Check if unified health check script exists
if [ ! -f "$HEALTH_CHECK_SCRIPT" ]; then
    echo "Error: Unified health check script not found at $HEALTH_CHECK_SCRIPT"
    exit 1
fi

echo "🏥 Starting startup health check..."

FAILED=false
UI_PORT_OVERRIDE="${STARTUP_UI_PORT:-${UI_PORT:-3000}}"
echo "Using UI health check port: ${UI_PORT_OVERRIDE}"

run_check() {
    local label="$1"
    shift
    echo "▶ ${label}"
    set +e
    "$HEALTH_CHECK_SCRIPT" --quiet "$@"
    local exit_code=$?
    set -e
    if [ $exit_code -eq 0 ]; then
        echo "✅ ${label} OK"
    else
        echo "❌ ${label} FAILED"
        FAILED=true
    fi
    echo ""
}

# API と Camera は起動時に必須、UI は任意 (結果はログのみ)
run_check "API health" "$@" --api-only
run_check "Camera health" "$@" --camera-only

# UI チェックは失敗しても致命的ではない
if ! UI_PORT="$UI_PORT_OVERRIDE" "$HEALTH_CHECK_SCRIPT" --quiet "$@" --ui-only; then
    echo "⚠️  UI health check failed (non-blocking at startup)"
fi

if [ "$FAILED" = true ]; then
    exit 1
fi

echo "✅ Startup health check completed"
