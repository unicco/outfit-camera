#!/bin/bash

# Service Readiness Checker for Coordinate Recorder Development Environment
# Waits for services to be ready before proceeding with dependent operations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[WAIT-SERVICE]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WAIT-SERVICE]${NC} $1"
}

print_error() {
    echo -e "${RED}[WAIT-SERVICE]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[WAIT-SERVICE]${NC} $1"
}

# Function to wait for API server to be ready
wait_for_api() {
    local api_port=${API_PORT:-8000}
    local max_attempts=${1:-30}
    local attempt=1

    print_info "Waiting for API server on port $api_port (max $max_attempts attempts)..."

    while [ $attempt -le $max_attempts ]; do
        # Try to reach the health endpoint with HEAD request for efficiency
        if curl -s --head --connect-timeout 2 --max-time 5 "http://localhost:${api_port}/v2/daily-status" > /dev/null 2>&1; then
            print_status "✅ API server is ready (attempt $attempt/$max_attempts)"
            return 0
        fi

        # Show progress every 5 attempts
        if [ $((attempt % 5)) -eq 0 ]; then
            print_info "⏳ Still waiting for API server... (attempt $attempt/$max_attempts)"
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    print_error "❌ API server not ready after $max_attempts attempts"
    return 1
}

# Function to wait for camera server to be ready
wait_for_camera() {
    local camera_port=${CAMERA_PORT:-8001}
    local max_attempts=${1:-30}
    local attempt=1

    print_info "Waiting for camera server on port $camera_port (max $max_attempts attempts)..."

    while [ $attempt -le $max_attempts ]; do
        # Try to reach the stream endpoint with HEAD request for efficiency
        if curl -s --head --connect-timeout 2 --max-time 5 "http://localhost:${camera_port}/stream" > /dev/null 2>&1; then
            print_status "✅ Camera server is ready (attempt $attempt/$max_attempts)"
            return 0
        fi

        # Show progress every 5 attempts
        if [ $((attempt % 5)) -eq 0 ]; then
            print_info "⏳ Still waiting for camera server... (attempt $attempt/$max_attempts)"
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    print_error "❌ Camera server not ready after $max_attempts attempts"
    return 1
}

# Function to wait for UI server to be ready
wait_for_ui() {
    local ui_port=${UI_PORT:-3000}
    local max_attempts=${1:-30}
    local attempt=1

    print_info "Waiting for UI server on port $ui_port (max $max_attempts attempts)..."

    while [ $attempt -le $max_attempts ]; do
        # Try to reach the UI server with HEAD request for efficiency
        if curl -s --head --connect-timeout 2 --max-time 5 "http://localhost:${ui_port}" > /dev/null 2>&1; then
            print_status "✅ UI server is ready (attempt $attempt/$max_attempts)"
            return 0
        fi

        # Show progress every 5 attempts
        if [ $((attempt % 5)) -eq 0 ]; then
            print_info "⏳ Still waiting for UI server... (attempt $attempt/$max_attempts)"
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    print_error "❌ UI server not ready after $max_attempts attempts"
    return 1
}

# Function to wait for database to be ready
wait_for_database() {
    local db_port=${DB_PORT:-5438}
    local max_attempts=${1:-30}
    local attempt=1

    print_info "Waiting for database on port $db_port (max $max_attempts attempts)..."

    while [ $attempt -le $max_attempts ]; do
        # Try to connect to database port
        if nc -z localhost $db_port 2>/dev/null; then
            print_status "✅ Database is ready (attempt $attempt/$max_attempts)"
            return 0
        fi

        # Show progress every 5 attempts
        if [ $((attempt % 5)) -eq 0 ]; then
            print_info "⏳ Still waiting for database... (attempt $attempt/$max_attempts)"
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    print_error "❌ Database not ready after $max_attempts attempts"
    return 1
}

# Function to wait for all core services (API + UI, optionally camera)
wait_for_core_services() {
    local max_attempts=${1:-30}
    local skip_camera=${SKIP_CAMERA:-false}

    print_info "Waiting for core services to be ready..."

    local services_failed=false

    # Wait for API server (required)
    if ! wait_for_api $max_attempts; then
        services_failed=true
    fi

    # Wait for UI server (required)
    if ! wait_for_ui $max_attempts; then
        services_failed=true
    fi

    # Wait for camera server (optional)
    if [ "$skip_camera" != "true" ]; then
        if ! wait_for_camera $max_attempts; then
            print_warning "⚠️ Camera server not ready, but continuing..."
        fi
    else
        print_info "⏭️ Skipping camera server readiness check (SKIP_CAMERA=true)"
    fi

    if [ "$services_failed" = true ]; then
        print_error "❌ Core services are not ready"
        return 1
    fi

    print_status "✅ Core services are ready"
    return 0
}

# Function to wait for all services including database
wait_for_all_services() {
    local max_attempts=${1:-30}
    local skip_camera=${SKIP_CAMERA:-false}

    print_info "Waiting for all services to be ready..."

    local services_failed=false

    # Wait for database (required)
    if ! wait_for_database $max_attempts; then
        services_failed=true
    fi

    # Wait for core services
    if ! wait_for_core_services $max_attempts; then
        services_failed=true
    fi

    if [ "$services_failed" = true ]; then
        print_error "❌ Not all services are ready"
        return 1
    fi

    print_status "✅ All services are ready"
    return 0
}

# Function to perform comprehensive health check
perform_health_check() {
    print_info "Performing comprehensive health check..."

    local api_port=${API_PORT:-8000}
    local camera_port=${CAMERA_PORT:-8001}
    local ui_port=${UI_PORT:-3000}
    local skip_camera=${SKIP_CAMERA:-false}

    local health_issues=()

    # Check API server health
    if ! curl -s --head --connect-timeout 2 --max-time 5 "http://localhost:${api_port}/v2/daily-status" > /dev/null 2>&1; then
        health_issues+=("API server (port $api_port) is not responding")
    else
        print_status "✅ API server health check passed"
    fi

    # Check UI server health
    if ! curl -s --head --connect-timeout 2 --max-time 5 "http://localhost:${ui_port}" > /dev/null 2>&1; then
        health_issues+=("UI server (port $ui_port) is not responding")
    else
        print_status "✅ UI server health check passed"
    fi

    # Check camera server health (if not skipped)
    if [ "$skip_camera" != "true" ]; then
        if ! curl -s --head --connect-timeout 2 --max-time 5 "http://localhost:${camera_port}/stream" > /dev/null 2>&1; then
            health_issues+=("Camera server (port $camera_port) is not responding")
        else
            print_status "✅ Camera server health check passed"
        fi
    fi

    # Report results
    if [ ${#health_issues[@]} -eq 0 ]; then
        print_status "✅ All health checks passed"
        return 0
    else
        print_error "❌ Health check issues detected:"
        for issue in "${health_issues[@]}"; do
            print_error "  - $issue"
        done
        return 1
    fi
}

# Main function for command-line usage
main() {
    # Load environment if not already loaded
    if [ -z "$PROJECT_ROOT" ]; then
        local env_file="$(dirname "${BASH_SOURCE[0]}")/../../../.env"
        if [ -f "$env_file" ]; then
            source "$env_file"
        fi
    fi

    case "${1:-}" in
        "api")
            wait_for_api "${2:-30}"
            ;;
        "camera")
            wait_for_camera "${2:-30}"
            ;;
        "ui")
            wait_for_ui "${2:-30}"
            ;;
        "database"|"db")
            wait_for_database "${2:-30}"
            ;;
        "core")
            wait_for_core_services "${2:-30}"
            ;;
        "all")
            wait_for_all_services "${2:-30}"
            ;;
        "health"|"check")
            perform_health_check
            ;;
        *)
            echo "Usage: $0 {api|camera|ui|database|core|all|health} [max_attempts]"
            echo ""
            echo "Commands:"
            echo "  api        - Wait for API server to be ready"
            echo "  camera     - Wait for camera server to be ready"
            echo "  ui         - Wait for UI server to be ready"
            echo "  database   - Wait for database to be ready"
            echo "  core       - Wait for core services (API + UI) to be ready"
            echo "  all        - Wait for all services to be ready"
            echo "  health     - Perform comprehensive health check"
            echo ""
            echo "Parameters:"
            echo "  max_attempts - Maximum number of attempts (default: 30)"
            echo ""
            echo "Examples:"
            echo "  $0 api 60       # Wait up to 60 seconds for API"
            echo "  $0 core         # Wait for core services with default timeout"
            echo "  $0 all 45       # Wait up to 45 seconds for all services"
            echo "  $0 health       # Perform health check"
            exit 1
            ;;
    esac
}

# Execute main if script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
