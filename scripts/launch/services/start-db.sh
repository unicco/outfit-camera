#!/bin/bash

# Database Service Startup
# Extracted from start-dev.sh for modular architecture

set -e

# Source environment loader if not already loaded
if [ -z "$PROJECT_ROOT" ]; then
    source "$(dirname "${BASH_SOURCE[0]}")/../common/load-env.sh"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[DB]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[DB]${NC} $1"
}

print_error() {
    echo -e "${RED}[DB]${NC} $1"
}

# Function to check if port is available
check_port() {
    local port=$1
    if lsof -i :$port > /dev/null 2>&1; then
        return 1  # Port is busy
    else
        return 0  # Port is available
    fi
}

# Start PostgreSQL database
start_database() {
    print_status "🔍 Checking PostgreSQL database availability..."

    # Fixed PostgreSQL port
    export POSTGRES_PORT=5438
    export DATABASE_URL="postgresql+psycopg://coordinate_user:coordinate_pass@localhost:$POSTGRES_PORT/coordinate_db"

    if ! check_port $POSTGRES_PORT; then
        print_status "✅ PostgreSQL is already running on port $POSTGRES_PORT"
        return 0
    else
        print_warning "⚠️ PostgreSQL is not running on port $POSTGRES_PORT"
        print_status "🚀 Attempting to start PostgreSQL..."

        # Try to start PostgreSQL based on platform
        if command -v systemctl >/dev/null 2>&1; then
            # Linux system with systemd (Raspberry Pi)
            if systemctl is-active --quiet postgresql; then
                print_status "✅ PostgreSQL service is already running"
            else
                print_status "Starting PostgreSQL service..."
                # Check if we can use sudo without password prompt
                if sudo -n true 2>/dev/null; then
                    if sudo systemctl start postgresql 2>/dev/null; then
                        sleep 3
                        if systemctl is-active --quiet postgresql 2>/dev/null; then
                            print_status "✅ PostgreSQL started successfully"
                        else
                            print_warning "⚠️ PostgreSQL service started but status unclear"
                        fi
                    else
                        print_error "❌ Failed to start PostgreSQL service"
                        print_status "Please run: sudo systemctl start postgresql"
                        return 1
                    fi
                else
                    print_warning "⚠️ sudo permission required to start PostgreSQL"
                    print_status "Please run: sudo systemctl start postgresql"
                    return 1
                fi
            fi
        elif command -v brew >/dev/null 2>&1; then
            # macOS with Homebrew
            print_status "Starting PostgreSQL with Homebrew..."
            brew services start postgresql@15 >/dev/null 2>&1 || brew services start postgresql >/dev/null 2>&1
            sleep 3
            if ! check_port $POSTGRES_PORT; then
                print_status "✅ PostgreSQL started successfully"
            else
                print_error "❌ Failed to start PostgreSQL automatically"
                print_status "Please start PostgreSQL manually:"
                print_status "  brew services start postgresql@15  # if using Homebrew"
                return 1
            fi
        else
            print_error "❌ No supported PostgreSQL management tool found"
            print_status "Please start PostgreSQL manually:"
            print_status "  sudo systemctl start postgresql     # if using systemd (Linux)"
            print_status "  brew services start postgresql@15  # if using Homebrew (macOS)"
            return 1
        fi
    fi

    print_status "✅ PostgreSQL database is ready"
    return 0
}

# Main execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    start_database
fi
