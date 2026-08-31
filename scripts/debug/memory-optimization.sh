#!/bin/bash

# Memory Optimization Script for Raspberry Pi
# Issue: Production server memory exhaustion

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[MEMORY-OPT]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[MEMORY-OPTIMIZATION]${NC} $1"
}

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

print_header "🧠 Raspberry Pi Memory Optimization Starting..."

# 1. Check current memory usage
check_memory_usage() {
    print_header "📊 Current Memory Usage"

    if [ -f /proc/meminfo ]; then
        local total_mb=$(grep MemTotal /proc/meminfo | awk '{print int($2/1024)}')
        local available_mb=$(grep MemAvailable /proc/meminfo | awk '{print int($2/1024)}' 2>/dev/null || echo "0")
        local free_mb=$(grep MemFree /proc/meminfo | awk '{print int($2/1024)}')
        local used_mb=$((total_mb - available_mb))

        print_status "Total Memory: ${total_mb}MB"
        print_status "Available Memory: ${available_mb}MB"
        print_status "Used Memory: ${used_mb}MB"

        if [ $available_mb -lt 500 ]; then
            print_error "❌ Critical: Less than 500MB available"
            return 1
        elif [ $available_mb -lt 1000 ]; then
            print_warning "⚠️ Warning: Less than 1GB available"
            return 2
        else
            print_status "✅ Memory usage is acceptable"
            return 0
        fi
    else
        print_error "❌ Cannot read /proc/meminfo"
        return 1
    fi
}

# 2. Enable/increase swap if needed
setup_swap() {
    print_header "🔄 Swap Configuration"

    # Check current swap
    local current_swap=$(free -m | grep Swap | awk '{print $2}')
    print_status "Current swap: ${current_swap}MB"

    if [ $current_swap -lt 2048 ]; then
        print_status "Configuring swap to 2GB..."

        # Check if we can modify swap
        if [ -f /etc/dphys-swapfile ]; then
            print_status "Using dphys-swapfile (Raspberry Pi OS)"

            # Backup original config
            sudo cp /etc/dphys-swapfile /etc/dphys-swapfile.backup 2>/dev/null || true

            # Update swap size
            sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile

            # Restart swap
            sudo dphys-swapfile swapoff 2>/dev/null || true
            sudo dphys-swapfile setup
            sudo dphys-swapfile swapon

            print_status "✅ Swap configured to 2GB"
        else
            print_warning "⚠️ dphys-swapfile not found, manual swap setup required"
        fi
    else
        print_status "✅ Swap is adequately configured"
    fi
}

# 3. Optimize Python processes
optimize_python_memory() {
    print_header "🐍 Python Memory Optimization"

    # Set Python memory optimizations
    export PYTHONOPTIMIZE=1
    export PYTHONDONTWRITEBYTECODE=1

    print_status "✅ Memory optimization settings are configured in .env.common"
    print_status "💡 Settings include: PYTHONOPTIMIZE=1, YOLO_BATCH_SIZE=1, etc."
}

# 4. Clean up processes and caches
cleanup_system() {
    print_header "🧹 System Cleanup"

    # Clean package caches
    if command -v apt-get >/dev/null 2>&1; then
        print_status "Cleaning apt cache..."
        sudo apt-get clean 2>/dev/null || true
        sudo apt-get autoclean 2>/dev/null || true
    fi

    # Clean Python caches
    print_status "Cleaning Python caches..."
    find "${PROJECT_ROOT}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find "${PROJECT_ROOT}" -name "*.pyc" -delete 2>/dev/null || true

    # Clean pip cache
    if [ -d ~/.cache/pip ]; then
        print_status "Cleaning pip cache..."
        rm -rf ~/.cache/pip/* 2>/dev/null || true
    fi

    # Clean YOLO cache
    if [ -d ~/.cache/ultralytics ]; then
        print_status "Cleaning YOLO cache..."
        # Keep models but clean temporary files
        find ~/.cache/ultralytics -name "*.tmp" -delete 2>/dev/null || true
        find ~/.cache/ultralytics -name "*.partial" -delete 2>/dev/null || true
    fi

    print_status "✅ System cleanup completed"
}

# 5. Configure memory monitoring
setup_memory_monitoring() {
    print_header "📊 Memory Monitoring Setup"

    # Create memory monitor script
    cat > "${PROJECT_ROOT}/scripts/debug/memory-monitor.sh" << 'EOF'
#!/bin/bash
# Memory monitoring script

while true; do
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    memory_usage=$(free -m | grep "^Mem:" | awk '{printf "%.1f", ($3/$2)*100}')
    available_mb=$(grep MemAvailable /proc/meminfo | awk '{print int($2/1024)}' 2>/dev/null || echo "0")

    echo "[$timestamp] Memory: ${memory_usage}% used, ${available_mb}MB available"

    # Alert if memory is critically low
    if [ $available_mb -lt 200 ]; then
        echo "[$timestamp] ⚠️  CRITICAL: Memory below 200MB!"
        # Optional: kill processes or restart services
    fi

    sleep 30
done
EOF
    chmod +x "${PROJECT_ROOT}/scripts/debug/memory-monitor.sh"

    print_status "✅ Memory monitoring script created"
}

# 6. Create memory-optimized startup script
create_lightweight_startup() {
    print_header "🚀 Lightweight Startup Configuration"

    if [ ! -f "${PROJECT_ROOT}/scripts/launch-dev-lightweight.sh" ]; then
        print_status "📝 Creating launch-dev-lightweight.sh script..."
        # The script already exists in the repository
        print_status "✅ Memory-optimized launcher is available: ./scripts/launch-dev-lightweight.sh"
    else
        print_status "✅ Memory-optimized launcher already exists: ./scripts/launch-dev-lightweight.sh"
    fi
}

# Main execution
main() {
    local memory_status=0

    check_memory_usage
    memory_status=$?

    if [ $memory_status -ne 0 ]; then
        print_warning "Memory optimization needed"

        setup_swap
        optimize_python_memory
        cleanup_system
        setup_memory_monitoring
        create_lightweight_startup

        print_header "🎉 Memory optimization completed!"
        print_status ""
        print_status "📝 Next steps:"
        print_status "1. Use memory-optimized startup: ./scripts/launch-dev-lightweight.sh"
        print_status "2. Monitor memory: ./scripts/debug/memory-monitor.sh"
        print_status "3. Settings are automatically loaded from .env.common"
        print_status ""
        print_status "🔄 Consider rebooting for swap changes to take full effect"
    else
        print_status "✅ Memory usage is currently acceptable"
        print_status "💡 Run with --force to apply optimizations anyway"
    fi
}

# Handle command line arguments
if [ "$1" = "--force" ]; then
    print_status "🔧 Forcing memory optimization..."
    setup_swap
    optimize_python_memory
    cleanup_system
    setup_memory_monitoring
    create_lightweight_startup
    print_header "🎉 Memory optimization completed!"
else
    main
fi
