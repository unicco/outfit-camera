#!/bin/bash
#
# 共有仮想環境の健全性をチェックするスクリプト
# Usage: ./scripts/check-venv-health.sh

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔍 Checking shared virtual environment health...${NC}\n"

# Check environment variables
echo -e "${BLUE}1. Environment Variables:${NC}"
if [ -n "$VENV_CACHE_DIR" ]; then
    echo -e "   ${GREEN}✅ VENV_CACHE_DIR: $VENV_CACHE_DIR${NC}"
else
    echo -e "   ${YELLOW}⚠️  VENV_CACHE_DIR not set. Using default.${NC}"
    VENV_CACHE_DIR="/Users/unicco/repos/coordinate-recorder/.venvs"
fi

# Check shared venv directory
echo -e "\n${BLUE}2. Shared venv Directory:${NC}"
if [ -d "$VENV_CACHE_DIR" ]; then
    echo -e "   ${GREEN}✅ Directory exists: $VENV_CACHE_DIR${NC}"
    echo -e "   ${BLUE}Contents:${NC}"
    ls -la "$VENV_CACHE_DIR" | grep -E "api|camera|ui" | while read line; do
        echo "      $line"
    done
else
    echo -e "   ${RED}❌ Directory not found: $VENV_CACHE_DIR${NC}"
fi

# Check venv status
echo -e "\n${BLUE}3. Service venv Status:${NC}"
for service in api camera ui; do
    if [ -d "$service" ]; then
        echo -e "   ${BLUE}$service:${NC}"
        if [ -L "$service/venv" ]; then
            target=$(readlink "$service/venv")
            echo -e "      ${GREEN}✅ Symlink: $service/venv -> $target${NC}"

            # Check if target exists
            if [ -d "$target" ]; then
                echo -e "      ${GREEN}✅ Target exists${NC}"

                # Check Python executable
                if [ -x "$target/bin/python" ]; then
                    python_version=$("$target/bin/python" --version 2>&1)
                    echo -e "      ${GREEN}✅ Python: $python_version${NC}"
                else
                    echo -e "      ${RED}❌ Python executable not found or not executable${NC}"
                fi
            else
                echo -e "      ${RED}❌ Target doesn't exist${NC}"
            fi
        elif [ -d "$service/venv" ]; then
            echo -e "      ${YELLOW}⚠️  Regular directory (not symlink)${NC}"
        else
            echo -e "      ${YELLOW}⚠️  No venv found${NC}"
        fi
    fi
done

# Check for Issue #905 dependencies
echo -e "\n${BLUE}4. Issue #905 Dependencies Check:${NC}"
if [ -L "api/venv" ]; then
    echo -e "   Checking for Google AI packages in API venv..."
    if api/venv/bin/pip list 2>/dev/null | grep -q "google-generativeai"; then
        version=$(api/venv/bin/pip show google-generativeai 2>/dev/null | grep Version | cut -d' ' -f2)
        echo -e "   ${GREEN}✅ google-generativeai installed (v$version)${NC}"
    else
        echo -e "   ${YELLOW}⚠️  google-generativeai not installed${NC}"
        echo -e "   ${BLUE}To install: cd api && ./venv/bin/pip install google-generativeai==0.8.3${NC}"
    fi

    # Check other required packages
    for pkg in "schedule" "pytz"; do
        if api/venv/bin/pip list 2>/dev/null | grep -q "$pkg"; then
            echo -e "   ${GREEN}✅ $pkg installed${NC}"
        else
            echo -e "   ${YELLOW}⚠️  $pkg not installed${NC}"
        fi
    done
fi

# Summary
echo -e "\n${BLUE}5. Summary:${NC}"
total_venvs=$(ls -1 "$VENV_CACHE_DIR" 2>/dev/null | wc -l || echo "0")
echo -e "   Total shared venvs: $total_venvs"

# Disk usage
if [ -d "$VENV_CACHE_DIR" ]; then
    disk_usage=$(du -sh "$VENV_CACHE_DIR" 2>/dev/null | cut -f1)
    echo -e "   Total disk usage: $disk_usage"
fi

# Recommendations
echo -e "\n${BLUE}6. Recommendations:${NC}"
if [ "$total_venvs" -gt 10 ]; then
    echo -e "   ${YELLOW}⚠️  Consider cleaning old venvs: rm -rf $VENV_CACHE_DIR/*-old-hash${NC}"
fi

echo -e "\n${GREEN}✨ Health check complete!${NC}"
