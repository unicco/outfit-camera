#!/bin/bash

# Wardrobe Management System Integration Test Script

set -e

echo "🧥 Wardrobe Management System - Integration Test"
echo "=============================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if we're on the right branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "integration/wardrobe-management" ]; then
    echo -e "${YELLOW}Warning: Not on integration/wardrobe-management branch${NC}"
    echo "Current branch: $CURRENT_BRANCH"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Function to check service health
check_service() {
    local service=$1
    local url=$2
    local max_attempts=30
    local attempt=1

    echo -n "Checking $service..."

    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$url" > /dev/null 2>&1; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo -e " ${RED}✗${NC}"
    return 1
}

# Start services
echo -e "\n📦 Starting services..."
./scripts/start-development.sh

# Wait for services to be ready
echo -e "\n🔍 Waiting for services to be ready..."
check_service "PostgreSQL" "http://localhost:5432" || true
check_service "Backend" "http://localhost:8000/health"
check_service "Frontend" "http://localhost:3000"
check_service "AI Service" "http://localhost:8002/health"

# Run basic API tests
echo -e "\n🧪 Running basic API tests..."

# Test Backend health
echo -n "Testing Backend API health..."
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${RED}✗${NC}"
fi

# Test AI Service health
echo -n "Testing AI Service health..."
if curl -s http://localhost:8002/health | grep -q "healthy"; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${RED}✗${NC}"
fi

# Test Wardrobe API endpoints
echo -n "Testing Wardrobe API endpoints..."
if curl -s http://localhost:8000/api/v2/wardrobe/items | grep -q "items"; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${RED}✗${NC}"
fi

# Display service URLs
echo -e "\n🌐 Service URLs:"
echo "  Frontend:   http://localhost:3000"
echo "  Backend:    http://localhost:8000/docs"
echo "  AI Service: http://localhost:8002/docs"

# Display logs command
echo -e "\n📋 To view logs:"
echo "  tail -f logs/backend.log"
echo "  tail -f logs/frontend.log"
echo "  tail -f logs/camera.log"

# Display test scenarios
echo -e "\n📝 Test Scenarios:"
echo "  1. Visit http://localhost:3000 and explore the wardrobe dashboard"
echo "  2. Try adding new clothing items"
echo "  3. Test the photo capture feature"
echo "  4. Check analytics and statistics"

echo -e "\n✅ Integration test environment is ready!"
echo "Note: AI-001 (clothing detection) is using mock data until implementation is complete."
