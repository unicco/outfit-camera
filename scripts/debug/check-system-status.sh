#!/bin/bash

# System Status Checker for Coordinate Recorder
# Provides comprehensive view of all running services

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROCESS_MANAGER="${PROJECT_ROOT}/scripts/process-manager.sh"

print_header() {
    echo -e "\n${BLUE}[SYSTEM-STATUS]${NC} $1"
    echo "$(printf '=%.0s' {1..50})"
}

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show current project information
show_project_info() {
    print_header "📁 Current Project Information"

    local current_dir=$(basename "$PROJECT_ROOT")
    local session_type="Unknown"

    if [[ "$current_dir" == "coordinate-recorder" ]]; then
        session_type="Main"
    fi

    echo -e "   📂 Directory: ${CYAN}$current_dir${NC}"
    echo -e "   🎯 Session Type: ${CYAN}$session_type${NC}"
    echo -e "   📍 Full Path: ${CYAN}$PROJECT_ROOT${NC}"

    # Load and show environment
    if [ -f "$PROJECT_ROOT/.env" ]; then
        source "$PROJECT_ROOT/.env" 2>/dev/null || true
        echo -e "   🌐 API Port: ${CYAN}${API_PORT:-'Not set'}${NC}"
        echo -e "   🌐 UI Port: ${CYAN}${UI_PORT:-'Not set'}${NC}"
        echo -e "   🌐 Camera Port: ${CYAN}${CAMERA_PORT:-'Not set'}${NC}"
    else
        print_warning "   No .env file found"
    fi
}

# Show all coordinate recorder processes system-wide
show_all_processes() {
    print_header "🔍 All Coordinate Recorder Processes"

    # Use more specific process matching to avoid false positives
    local processes=$(ps aux | grep -E "(uvicorn.*app\.main|camera_service\.py|vite.*--port)" | grep -v grep)

    if [ -z "$processes" ]; then
        print_status "   No Coordinate Recorder processes found"
        return
    fi

    echo "$processes" | while IFS= read -r line; do
        local pid=$(echo "$line" | awk '{print $2}')
        local port=""

        # Extract port from command line
        if echo "$line" | grep -q -- "--port"; then
            port=$(echo "$line" | sed -n 's/.*--port \([0-9]*\).*/\1/p')
        fi

        # Determine service type
        local service_type="Unknown"
        if echo "$line" | grep -q "uvicorn"; then
            service_type="API Server"
        elif echo "$line" | grep -q "camera_service"; then
            service_type="Camera Server"
        elif echo "$line" | grep -q "vite"; then
            service_type="UI Server"
        fi

        echo -e "   ${GREEN}•${NC} ${service_type} (PID: ${CYAN}$pid${NC}, Port: ${CYAN}${port:-'Unknown'}${NC})"
        echo "     Command: $(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}')"
    done
}

# Show enhanced process manager status
show_process_manager_status() {
    print_header "🔧 Enhanced Process Manager Status"

    if [ -f "$PROCESS_MANAGER" ]; then
        print_status "   Process manager is available"
        echo ""
        "$PROCESS_MANAGER" list
    else
        print_warning "   Process manager not found at: $PROCESS_MANAGER"
    fi
}

# Show port usage
show_port_usage() {
    print_header "🌐 Port Usage Analysis"

    local common_ports=(3000 3010 3014 3032 8000 8001 8014 8015 8032 5432)

    for port in "${common_ports[@]}"; do
        if lsof -i :$port > /dev/null 2>&1; then
            local pid=$(lsof -ti :$port 2>/dev/null | head -1)
            local process_info=$(ps -p $pid -o comm=,args= 2>/dev/null | head -1 | cut -c1-60)
            echo -e "   ${RED}•${NC} Port ${CYAN}$port${NC}: ${YELLOW}BUSY${NC} (PID: $pid) - $process_info"
        else
            echo -e "   ${GREEN}•${NC} Port ${CYAN}$port${NC}: ${GREEN}FREE${NC}"
        fi
    done
}

# Show recommendations
show_recommendations() {
    print_header "💡 Recommendations"

    local has_conflicts=false
    local recommendations=()

    # Check for port conflicts
    local port_conflicts=$(lsof -i :8000,8001,8014,8015,3000,3010,3014,3032 2>/dev/null | wc -l)
    if [ "$port_conflicts" -gt 1 ]; then
        has_conflicts=true
        recommendations+=("🔧 Multiple services detected on common ports - consider using process manager")
    fi

    # Check if process manager is available
    if [ ! -f "$PROCESS_MANAGER" ]; then
        recommendations+=("📦 Install enhanced process manager for better coordination")
        recommendations+=("   Run: cp scripts/process-manager.sh.template scripts/process-manager.sh")
    fi

    # Check for dead processes
    if [ -f "/tmp/coordinate-recorder-pids" ]; then
        local dead_services=$("$PROCESS_MANAGER" cleanup 2>/dev/null | grep -c "dead" || echo "0")
        if [ "$dead_services" -gt 0 ]; then
            recommendations+=("🧹 Clean up $dead_services dead services: ./scripts/process-manager.sh cleanup")
        fi
    fi

    if [ ${#recommendations[@]} -eq 0 ]; then
        print_status "   ✅ System looks healthy!"
    else
        for rec in "${recommendations[@]}"; do
            echo -e "   $rec"
        done
    fi
}

# Main execution
main() {
    echo -e "${CYAN}🏥 Coordinate Recorder System Status${NC}"
    echo -e "${CYAN}=====================================${NC}"

    show_project_info
    show_all_processes
    show_process_manager_status
    show_port_usage
    show_recommendations

    echo ""
    print_status "Status check completed at $(date)"
}

# Command line options
case "${1:-full}" in
    "processes")
        show_all_processes
        ;;
    "ports")
        show_port_usage
        ;;
    "manager")
        show_process_manager_status
        ;;
    "help")
        echo "System Status Checker"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  full         Show complete system status (default)"
        echo "  processes    Show only running processes"
        echo "  ports        Show only port usage"
        echo "  manager      Show only process manager status"
        echo "  help         Show this help message"
        ;;
    *)
        main
        ;;
esac
