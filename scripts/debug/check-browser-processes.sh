#!/bin/bash

# Issue 260 対応: Chromium/Browser プロセス監視ツール
# Chromium プロセスによるメモリ使用量とリーク検出

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[BROWSER-MONITOR]${NC} $1"
}

# Memory threshold settings (MB)
WARNING_THRESHOLD=200   # 200MB warning
CRITICAL_THRESHOLD=400  # 400MB critical
PROCESS_COUNT_LIMIT=10  # Maximum number of browser processes

print_header "🌐 Browser Process Monitor (Issue 260 対応)"
echo "⚠️  Memory Warning: ${WARNING_THRESHOLD}MB | Critical: ${CRITICAL_THRESHOLD}MB"
echo "🔢 Process Limit: ${PROCESS_COUNT_LIMIT} processes"
echo ""

# Check for browser processes
browser_processes=$(ps aux | grep -E "(chrome|chromium|playwright)" | grep -v grep | grep -v "$0" || true)

if [ -z "$browser_processes" ]; then
    print_status "✅ No browser processes found"
    exit 0
fi

# Count and analyze processes
process_count=$(echo "$browser_processes" | wc -l | xargs)
total_memory=0
high_memory_processes=0
critical_memory_processes=0

print_warning "🔍 Found $process_count browser processes"

if [ "$process_count" -gt "$PROCESS_COUNT_LIMIT" ]; then
    print_error "❌ Process count ($process_count) exceeds limit ($PROCESS_COUNT_LIMIT)"
fi

echo ""
print_status "📊 Process Details:"
echo ""

# Header for process table
printf "%-8s %-15s %-10s %-8s %-50s\n" "PID" "USER" "CPU%" "MEM(MB)" "COMMAND"
echo "--------------------------------------------------------------------------------"

while IFS= read -r line; do
    if [ -n "$line" ]; then
        # Parse ps output: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
        user=$(echo "$line" | awk '{print $1}')
        pid=$(echo "$line" | awk '{print $2}')
        cpu=$(echo "$line" | awk '{print $3}')
        mem_percent=$(echo "$line" | awk '{print $4}')
        rss=$(echo "$line" | awk '{print $6}')  # RSS in KB
        command=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}' | cut -c1-50)

        # Convert RSS (KB) to MB
        mem_mb=$((rss / 1024))
        total_memory=$((total_memory + mem_mb))

        # Check memory thresholds
        status_indicator=""
        if [ "$mem_mb" -gt "$CRITICAL_THRESHOLD" ]; then
            status_indicator="🔴"
            critical_memory_processes=$((critical_memory_processes + 1))
        elif [ "$mem_mb" -gt "$WARNING_THRESHOLD" ]; then
            status_indicator="🟡"
            high_memory_processes=$((high_memory_processes + 1))
        else
            status_indicator="🟢"
        fi

        printf "%-8s %-15s %-10s %-8s %-50s %s\n" "$pid" "$user" "$cpu" "$mem_mb" "$command" "$status_indicator"
    fi
done <<< "$browser_processes"

echo ""
print_status "📈 Memory Summary:"
echo "  Total Memory Usage: ${total_memory}MB"
echo "  High Memory Processes (>${WARNING_THRESHOLD}MB): $high_memory_processes"
echo "  Critical Memory Processes (>${CRITICAL_THRESHOLD}MB): $critical_memory_processes"

# Overall assessment
echo ""
if [ "$critical_memory_processes" -gt 0 ]; then
    print_error "❌ CRITICAL: $critical_memory_processes processes using >${CRITICAL_THRESHOLD}MB"
    print_error "🚨 Action Required: Consider killing high-memory processes"
    echo ""
    print_status "💡 Kill commands:"
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            pid=$(echo "$line" | awk '{print $2}')
            rss=$(echo "$line" | awk '{print $6}')
            mem_mb=$((rss / 1024))
            if [ "$mem_mb" -gt "$CRITICAL_THRESHOLD" ]; then
                echo "  kill $pid  # ${mem_mb}MB"
            fi
        fi
    done <<< "$browser_processes"
elif [ "$high_memory_processes" -gt 0 ]; then
    print_warning "⚠️  WARNING: $high_memory_processes processes using >${WARNING_THRESHOLD}MB"
    print_status "Monitor these processes for continued growth"
elif [ "$total_memory" -gt 1000 ]; then
    print_warning "⚠️  Total browser memory usage is high: ${total_memory}MB"
else
    print_status "✅ Memory usage is within acceptable limits"
fi

# Process count assessment
if [ "$process_count" -gt "$PROCESS_COUNT_LIMIT" ]; then
    echo ""
    print_error "❌ Too many browser processes: $process_count > $PROCESS_COUNT_LIMIT"
    print_status "💡 Consider restarting browser automation or reducing parallel tests"
fi

echo ""
print_status "💡 Issue 260 対応 Tips:"
echo "  • Use './scripts/stop-development.sh' to clean up browser processes"
echo "  • Monitor with: watch -n 5 ./scripts/debug/check-browser-processes.sh"
echo "  • Emergency cleanup: pkill -f 'chrome|chromium|playwright'"
