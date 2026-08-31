#!/usr/bin/env bash
# Coordinate Recorder — VPS health check script
# Checks API, DB, disk, and memory. Logs warnings to journal.
set -euo pipefail

API_URL="http://127.0.0.1:8000/health"
DISK_WARN_PERCENT=85
MEM_WARN_PERCENT=85
LOG_TAG="coordinate-health"

log_info()  { echo "$1" | systemd-cat -t "$LOG_TAG" -p info; }
log_warn()  { echo "$1" | systemd-cat -t "$LOG_TAG" -p warning; }
log_error() { echo "$1" | systemd-cat -t "$LOG_TAG" -p err; }

FAILED=0

# 1. API health
if RESPONSE=$(curl -sf --max-time 10 "$API_URL" 2>/dev/null); then
    STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "parse_error")
    DB_STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('database',{}).get('status','unknown'))" 2>/dev/null || echo "parse_error")

    if [ "$STATUS" = "healthy" ]; then
        log_info "API: healthy"
    else
        log_error "API: status=$STATUS"
        FAILED=$((FAILED + 1))
    fi

    if [ "$DB_STATUS" = "connected" ]; then
        log_info "DB: connected"
    else
        log_error "DB: status=$DB_STATUS"
        FAILED=$((FAILED + 1))
    fi
else
    log_error "API: not responding at $API_URL"
    FAILED=$((FAILED + 1))
fi

# 2. Disk usage
DISK_PERCENT=$(df / --output=pcent | tail -1 | tr -d ' %')
if [ "$DISK_PERCENT" -ge "$DISK_WARN_PERCENT" ]; then
    log_warn "Disk: ${DISK_PERCENT}% used (threshold: ${DISK_WARN_PERCENT}%)"
    FAILED=$((FAILED + 1))
else
    log_info "Disk: ${DISK_PERCENT}% used"
fi

# 3. Memory usage
MEM_PERCENT=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')
if [ "$MEM_PERCENT" -ge "$MEM_WARN_PERCENT" ]; then
    log_warn "Memory: ${MEM_PERCENT}% used (threshold: ${MEM_WARN_PERCENT}%)"
    FAILED=$((FAILED + 1))
else
    log_info "Memory: ${MEM_PERCENT}% used"
fi

# 4. Summary
if [ "$FAILED" -gt 0 ]; then
    log_error "Health check: ${FAILED} issue(s) detected"
    exit 1
else
    log_info "Health check: all OK"
fi
