#!/bin/bash

# Setup script for Jina Embedding Hybrid Matching
# This script helps configure the hybrid wardrobe matching system

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Jina Embedding Hybrid Matching Setup${NC}"
echo "========================================"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo -e "\n${YELLOW}📋 Checking prerequisites...${NC}"

if ! command_exists python3; then
    echo -e "${RED}❌ Python 3 is required but not installed${NC}"
    exit 1
fi

if ! command_exists pip; then
    echo -e "${RED}❌ pip is required but not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}"

# Check for .env file
echo -e "\n${YELLOW}🔍 Checking environment configuration...${NC}"

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}📝 Creating .env file from template...${NC}"
    if [ -f ".env.template" ]; then
        cp .env.template .env
        echo -e "${GREEN}✅ Created .env file${NC}"
    else
        echo -e "${RED}❌ .env.template not found${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# Check for JINA_API_KEY
if ! grep -q "^JINA_API_KEY=" .env || grep -q "^JINA_API_KEY=your_jina_api_key_here" .env; then
    echo -e "\n${YELLOW}🔑 Jina API Key Configuration${NC}"
    echo "Please enter your Jina AI API key:"
    echo "You can get one from: https://jina.ai/embeddings/"
    read -p "API Key: " -s jina_api_key
    echo

    if [ -z "$jina_api_key" ]; then
        echo -e "${RED}❌ API key cannot be empty${NC}"
        exit 1
    fi

    # Update .env file
    if grep -q "^JINA_API_KEY=" .env; then
        # Replace existing key
        sed -i.bak "s/^JINA_API_KEY=.*/JINA_API_KEY=$jina_api_key/" .env
    else
        # Add new key
        echo "JINA_API_KEY=$jina_api_key" >> .env
    fi

    echo -e "${GREEN}✅ API key configured${NC}"
else
    echo -e "${GREEN}✅ JINA_API_KEY already configured${NC}"
fi

# Create necessary directories
echo -e "\n${YELLOW}📁 Creating directories...${NC}"

directories=(
    "cache"
    "cache/embeddings"
    "data"
    "logs"
)

for dir in "${directories[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        echo -e "${GREEN}✅ Created directory: $dir${NC}"
    else
        echo -e "${BLUE}📁 Directory exists: $dir${NC}"
    fi
done

# Install Python dependencies
echo -e "\n${YELLOW}📦 Installing Python dependencies...${NC}"

# Check if we're in a virtual environment
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo -e "${GREEN}✅ Virtual environment active: $VIRTUAL_ENV${NC}"
else
    echo -e "${YELLOW}⚠️  No virtual environment detected${NC}"
    echo "It's recommended to use a virtual environment"
    read -p "Continue anyway? (y/N): " continue_without_venv
    if [[ ! "$continue_without_venv" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}💡 To create a virtual environment:${NC}"
        echo "  python3 -m venv venv"
        echo "  source venv/bin/activate"
        echo "  Then run this script again"
        exit 1
    fi
fi

# Install/upgrade pip
echo "Upgrading pip..."
python3 -m pip install --upgrade pip

# Install requirements
echo "Installing requirements..."
if [ -f "requirements-api.txt" ]; then
    python3 -m pip install -r requirements-api.txt
    echo -e "${GREEN}✅ Dependencies installed${NC}"
else
    echo -e "${RED}❌ requirements-api.txt not found${NC}"
    exit 1
fi

# Test the installation
echo -e "\n${YELLOW}🧪 Testing installation...${NC}"

cat > test_jina_setup.py << 'EOF'
#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, 'src')

def test_imports():
    try:
        from coordinate_recorder.jina_api_service import JinaAPIService
        from coordinate_recorder.hybrid_wardrobe_matcher import HybridWardrobeMatcher
        from coordinate_recorder.clothing_extractor import ClothingExtractor
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_api_key():
    api_key = os.getenv('JINA_API_KEY')
    if not api_key or api_key == 'your_jina_api_key_here':
        print("❌ JINA_API_KEY not configured properly")
        return False
    print("✅ API key configured")
    return True

def test_directories():
    dirs = ['cache', 'cache/embeddings', 'data']
    for dir_path in dirs:
        if not os.path.exists(dir_path):
            print(f"❌ Directory missing: {dir_path}")
            return False
    print("✅ All directories exist")
    return True

if __name__ == "__main__":
    # Load .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        # Read .env manually if python-dotenv not available
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value

    print("🧪 Testing Jina Embedding Setup...")
    print("=" * 40)

    tests = [
        ("Imports", test_imports),
        ("API Key", test_api_key),
        ("Directories", test_directories),
    ]

    all_passed = True
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        if not test_func():
            all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("🎉 All tests passed! Setup complete.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please check the configuration.")
        sys.exit(1)
EOF

echo "Running setup test..."
if python3 test_jina_setup.py; then
    echo -e "${GREEN}✅ Setup test passed${NC}"
    rm test_jina_setup.py
else
    echo -e "${RED}❌ Setup test failed${NC}"
    rm test_jina_setup.py
    exit 1
fi

# Create example usage script
echo -e "\n${YELLOW}📝 Creating example usage script...${NC}"

cat > example_jina_usage.py << 'EOF'
#!/usr/bin/env python3
"""Minimal placeholder demonstrating the AI detection v2 pipeline."""

import os


def main() -> None:
    print("🧥 AI Detection V2 Quick Check")
    print("=" * 50)
    print("The legacy ClothingDetector API has been deprecated.")
    print("All detection now flows through api/app/ai_detection_api_v2.py.")
    print("Start the FastAPI service and call /api/v2/ai/record to trigger")
    print("full detection + wardrobe matching.")

    if os.getenv("ROBOFLOW_KEY"):
        print("\n✅ ROBOFLOW_KEY detected. You are ready to use the V2 pipeline.")
    else:
        print("\n⚠️  ROBOFLOW_KEY is missing. Set it before invoking the detection API.")


if __name__ == "__main__":
    main()
EOF

chmod +x example_jina_usage.py

echo -e "${GREEN}✅ Created example_jina_usage.py${NC}"

# Final instructions
echo -e "\n${GREEN}🎉 Setup Complete!${NC}"
echo "==================="
echo
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Ensure your wardrobe database exists at: data/wardrobe.json"
echo "2. Review example_jina_usage.py for API v2 usage notes"
echo
echo -e "${YELLOW}Daily Usage:${NC}"
echo "- Start ./scripts/start-development.sh and call /api/v2/ai/record"
echo "- Inspect wardrobe matches via API responses or database entries"
echo
echo -e "${YELLOW}Configuration Files:${NC}"
echo "- API Key: .env (JINA_API_KEY)"
echo "- Cache: cache/wardrobe_embeddings.pkl"
echo "- Logs: cache/embeddings/"
echo
echo -e "${BLUE}💰 Cost Estimate:${NC}"
echo "- Initial setup: ~$2 (100 wardrobe items)"
echo "- Daily usage: ~$0.02 per photo"
echo "- Monthly: ~$0.60"
echo
echo -e "${GREEN}Happy matching! 🎯${NC}"
