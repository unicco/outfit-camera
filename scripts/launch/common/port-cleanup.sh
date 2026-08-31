#!/bin/bash

# Port Cleanup Utility for Coordinate Recorder Development Environment
# Automatically resolves port conflicts by terminating competing processes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[PORT-CLEANUP]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[PORT-CLEANUP]${NC} $1"
}

print_error() {
    echo -e "${RED}[PORT-CLEANUP]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[PORT-CLEANUP]${NC} $1"
}

# Function to cleanup a specific port
cleanup_port() {
    local port=$1
    local service_name=$2

    if [ -z "$port" ] || [ -z "$service_name" ]; then
        print_error "Usage: cleanup_port <port> <service_name>"
        return 1
    fi

    # Check if port is in use
    local pids=$(lsof -ti:${port} 2>/dev/null || true)

    if [ -z "$pids" ]; then
        print_status "Port $port is available for $service_name"
        return 0
    fi

    # Get detailed process information
    local process_info=$(ps -p "$pids" -o pid,comm,args --no-headers 2>/dev/null | head -3 || echo "Unknown processes")
    print_warning "Port $port is occupied by $service_name processes:"
    echo "$process_info" | while read -r line; do
        if [ -n "$line" ]; then
            print_info "  $line"
        fi
    done
    print_info "Attempting graceful termination for $service_name..."

    # Try graceful termination first (SIGTERM)
    echo "$pids" | xargs kill -TERM 2>/dev/null || true
    sleep 2

    # Check if processes are still running
    local remaining_pids=$(lsof -ti:${port} 2>/dev/null || true)

    if [ -n "$remaining_pids" ]; then
        local remaining_info=$(ps -p "$remaining_pids" -o pid,comm --no-headers 2>/dev/null || echo "Unknown processes")
        print_warning "Some processes still running on port $port:"
        echo "$remaining_info" | while read -r line; do
            if [ -n "$line" ]; then
                print_info "  $line"
            fi
        done
        print_info "Force killing remaining processes..."

        # Force kill (SIGKILL)
        echo "$remaining_pids" | xargs kill -KILL 2>/dev/null || true
        sleep 1

        # Final check
        local final_check=$(lsof -ti:${port} 2>/dev/null || true)
        if [ -n "$final_check" ]; then
            local final_info=$(ps -p "$final_check" -o pid,comm --no-headers 2>/dev/null || echo "Unknown processes")
            print_error "Failed to free port $port. Processes still running:"
            echo "$final_info" | while read -r line; do
                if [ -n "$line" ]; then
                    print_error "  $line"
                fi
            done
            return 1
        fi
    fi

    print_status "Port $port successfully freed for $service_name"
    return 0
}

# Function to cleanup all standard ports
cleanup_all_ports() {
    print_info "Starting port cleanup for Coordinate Recorder services..."

    # Load environment variables to get port numbers
    local env_file="${PROJECT_ROOT:-$(pwd)}/.env"
    if [ -f "$env_file" ]; then
        source "$env_file"
    fi

    # Default ports if not set in environment
    local api_port=${API_PORT:-8000}
    local camera_port=${CAMERA_PORT:-8001}
    local ui_port=${UI_PORT:-3000}
    local db_port=${DB_PORT:-5438}

    # Cleanup each service port
    local cleanup_failed=false

    if ! cleanup_port "$api_port" "API Server"; then
        cleanup_failed=true
    fi

    if ! cleanup_port "$camera_port" "Camera Server"; then
        cleanup_failed=true
    fi

    if ! cleanup_port "$ui_port" "UI Server"; then
        cleanup_failed=true
    fi

    if ! cleanup_port "$db_port" "Database Server"; then
        cleanup_failed=true
    fi

    if [ "$cleanup_failed" = true ]; then
        print_error "Some ports could not be cleaned up"
        return 1
    fi

    print_status "All ports cleaned up successfully"
    return 0
}

# Function to check port availability without cleanup
check_port_availability() {
    local port=$1
    local service_name=$2

    if [ -z "$port" ] || [ -z "$service_name" ]; then
        print_error "Usage: check_port_availability <port> <service_name>"
        return 1
    fi

    local pids=$(lsof -ti:${port} 2>/dev/null || true)

    if [ -z "$pids" ]; then
        print_status "✅ Port $port is available for $service_name"
        return 0
    else
        local process_info=$(ps -p "$pids" -o pid,comm --no-headers 2>/dev/null | head -3 || echo "Unknown processes")
        print_warning "⚠️ Port $port is occupied by $service_name processes:"
        echo "$process_info" | while read -r line; do
            if [ -n "$line" ]; then
                print_warning "    $line"
            fi
        done
        return 1
    fi
}

# Function to check all ports availability
check_all_ports() {
    print_info "Checking port availability for Coordinate Recorder services..."

    # Load environment variables
    local env_file="${PROJECT_ROOT:-$(pwd)}/.env"
    if [ -f "$env_file" ]; then
        source "$env_file"
    fi

    # Default ports
    local api_port=${API_PORT:-8000}
    local camera_port=${CAMERA_PORT:-8001}
    local ui_port=${UI_PORT:-3000}
    local db_port=${DB_PORT:-5438}

    local all_available=true

    if ! check_port_availability "$api_port" "API Server"; then
        all_available=false
    fi

    if ! check_port_availability "$camera_port" "Camera Server"; then
        all_available=false
    fi

    if ! check_port_availability "$ui_port" "UI Server"; then
        all_available=false
    fi

    if ! check_port_availability "$db_port" "Database Server"; then
        all_available=false
    fi

    if [ "$all_available" = true ]; then
        print_status "✅ All ports are available"
        return 0
    else
        print_warning "⚠️ Some ports are occupied"
        return 1
    fi
}

# Main function for command-line usage
main() {
    case "${1:-}" in
        "cleanup")
            cleanup_all_ports
            ;;
        "check")
            check_all_ports
            ;;
        "cleanup-port")
            if [ -z "$2" ] || [ -z "$3" ]; then
                print_error "Usage: $0 cleanup-port <port> <service_name>"
                exit 1
            fi
            cleanup_port "$2" "$3"
            ;;
        "check-port")
            if [ -z "$2" ] || [ -z "$3" ]; then
                print_error "Usage: $0 check-port <port> <service_name>"
                exit 1
            fi
            check_port_availability "$2" "$3"
            ;;
        *)
            echo "Usage: $0 {cleanup|check|cleanup-port <port> <service>|check-port <port> <service>}"
            echo ""
            echo "Commands:"
            echo "  cleanup           - Clean up all standard service ports"
            echo "  check            - Check availability of all standard service ports"
            echo "  cleanup-port     - Clean up a specific port"
            echo "  check-port       - Check availability of a specific port"
            echo ""
            echo "Examples:"
            echo "  $0 cleanup"
            echo "  $0 check"
            echo "  $0 cleanup-port 8000 'API Server'"
            echo "  $0 check-port 3000 'UI Server'"
            exit 1
            ;;
    esac
}

# Execute main if script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
