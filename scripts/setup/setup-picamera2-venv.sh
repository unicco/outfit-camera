#!/bin/bash

# Picamera2 対応仮想環境セットアップスクリプト
# Raspberry Pi での Picamera2 ハードウェアカメラサポート専用

set -e  # Exit on any error

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
    echo -e "${BLUE}[SETUP]${NC} $1"
}

# Auto-detect project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_PATH="${PROJECT_ROOT}/../coordinate-recorder-venv"

print_header "🎥 Picamera2 Virtual Environment Setup"
print_status "Project root: $PROJECT_ROOT"
print_status "Virtual environment path: $VENV_PATH"

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    print_warning "This script is designed for Raspberry Pi systems"
    print_warning "On other systems, Picamera2 hardware features may not be available"
fi

# Check if Picamera2 is installed system-wide
print_header "🔍 Checking system Picamera2 installation"

if python3 -c "import picamera2" 2>/dev/null; then
    print_status "✅ System Picamera2 is available"
    PICAMERA2_LOCATION=$(python3 -c "import picamera2; print(picamera2.__file__)")
    print_status "Location: $PICAMERA2_LOCATION"
else
    print_error "❌ System Picamera2 not found"
    print_error "Please install it first:"
    print_error "  sudo apt update"
    print_error "  sudo apt install -y python3-picamera2 libcamera-apps"
    exit 1
fi

# Remove existing virtual environment if it exists
if [ -d "$VENV_PATH" ]; then
    print_warning "Removing existing virtual environment..."
    rm -rf "$VENV_PATH"
fi

# Create virtual environment with system-site-packages access
print_header "🐍 Creating virtual environment"
print_status "Creating venv with --system-site-packages flag..."

python3 -m venv --system-site-packages "$VENV_PATH"

# Activate virtual environment
print_status "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Install compatible versions of key dependencies
print_header "📦 Installing compatible dependencies"

print_status "Installing NumPy and OpenCV with version constraints..."
pip install 'numpy>=1.21,<2' 'opencv-python<4.12' || {
    print_error "NumPy/OpenCV インストール失敗"
    exit 1
}

print_status "Installing core web framework dependencies..."
pip install fastapi 'uvicorn[standard]' httpx python-multipart python-dotenv || {
    print_error "Web フレームワーク依存関係インストール失敗"
    exit 1
}

print_status "Installing image processing dependencies..."
pip install pillow || {
    print_error "Pillow インストール失敗"
    exit 1
}

# Create symlinks for system-only packages that can't be pip installed
print_header "🔗 Creating symlinks for system-only packages"

# Detect Python version and site-packages directory
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
VENV_SITE_PACKAGES="$VENV_PATH/lib/python$PYTHON_VERSION/site-packages"

print_status "Detected Python version: $PYTHON_VERSION"
print_status "Virtual environment site-packages: $VENV_SITE_PACKAGES"

if [ ! -d "$VENV_SITE_PACKAGES" ]; then
    print_error "Virtual environment site-packages directory not found: $VENV_SITE_PACKAGES"
    exit 1
fi

print_status "Creating libcamera symlink for virtual environment access..."
if [ -d "/usr/lib/python3/dist-packages/libcamera" ]; then
    ln -sf /usr/lib/python3/dist-packages/libcamera "$VENV_SITE_PACKAGES/libcamera" || {
        print_error "Failed to create libcamera symlink"
        exit 1
    }
    print_status "✅ libcamera symlink created"
else
    print_warning "⚠️ System libcamera not found"
fi

print_status "Creating pykms symlink for virtual environment access..."
if [ -d "/usr/lib/python3/dist-packages/pykms" ]; then
    ln -sf /usr/lib/python3/dist-packages/pykms "$VENV_SITE_PACKAGES/pykms" || {
        print_error "Failed to create pykms symlink"
        exit 1
    }
    print_status "✅ pykms symlink created"
else
    print_warning "⚠️ System pykms not found"
fi

# Test installations
print_header "🧪 Testing installations"

python3 -c "
import sys
print(f'🐍 Python executable: {sys.executable}')
print(f'📍 Virtual environment: {sys.prefix}')
print()

tests = [
    ('cv2', 'OpenCV'),
    ('numpy', 'NumPy'),
    ('PIL', 'Pillow'),
    ('fastapi', 'FastAPI'),
    ('uvicorn', 'Uvicorn'),
    ('httpx', 'HTTPX'),
    ('multipart', 'python-multipart'),
    ('dotenv', 'python-dotenv')
]

success_count = 0
for module, name in tests:
    try:
        imported = __import__(module)
        version = getattr(imported, '__version__', 'unknown')
        print(f'✅ {name}: {version}')
        success_count += 1
    except ImportError as e:
        print(f'❌ {name}: {e}')

print()

# Special test for Picamera2 with hardware capability
try:
    import picamera2
    from picamera2 import Picamera2
    print('✅ Picamera2: Successfully imported')

    # Try to detect cameras
    try:
        cameras = Picamera2.global_camera_info()
        if cameras:
            print(f'📷 Found {len(cameras)} camera(s):')
            for i, cam in enumerate(cameras):
                model = cam.get('Model', 'Unknown')
                location = cam.get('Location', 'Unknown')
                print(f'   Camera {i}: {model} (Location: {location})')
        else:
            print('⚠️ No cameras detected')
    except Exception as e:
        print(f'⚠️ Camera detection failed: {e}')

    success_count += 1
except ImportError as e:
    print(f'❌ Picamera2: {e}')

print()
print(f'📊 Test Results: {success_count}/{len(tests) + 1} passed')
"

# Create activation helper script
print_header "📝 Creating helper scripts"

ACTIVATE_SCRIPT="$PROJECT_ROOT/activate-picamera2-env.sh"
cat > "$ACTIVATE_SCRIPT" << 'EOF'
#!/bin/bash
# Picamera2 環境アクティベーションヘルパー

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${PROJECT_ROOT}/../coordinate-recorder-venv"

if [ -d "$VENV_PATH" ]; then
    echo "🐍 Activating Picamera2 virtual environment..."
    source "$VENV_PATH/bin/activate"

    # Set PYTHONPATH for coordinate_recorder module
    export PYTHONPATH="${PROJECT_ROOT}/src:${PROJECT_ROOT}:${PYTHONPATH}"

    echo "✅ Environment activated!"
    echo "📍 Virtual env: $VIRTUAL_ENV"
    echo "🐍 Python: $(python --version)"
    echo "📁 PYTHONPATH includes: ${PROJECT_ROOT}/src"
    echo
    echo "💡 You can now run:"
    echo "  python camera/camera_service.py"
    echo "  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
else
    echo "❌ Virtual environment not found at: $VENV_PATH"
    echo "Please run: ./scripts/setup/setup-picamera2-venv.sh"
fi
EOF

chmod +x "$ACTIVATE_SCRIPT"
print_status "Created activation helper: $ACTIVATE_SCRIPT"

# Summary
print_header "🎉 Setup Complete!"

echo
print_status "🎯 What was accomplished:"
echo "  ✅ Virtual environment created with system-site-packages access"
echo "  ✅ Compatible NumPy and OpenCV versions installed"
echo "  ✅ Picamera2 hardware camera support enabled"
echo "  ✅ Web framework dependencies installed"
echo "  ✅ libcamera and pykms symlinks for virtual environment access"
echo "  ✅ Activation helper script created"

echo
print_status "🚀 Next steps:"
echo "  1. Activate the environment:"
echo "     source activate-picamera2-env.sh"
echo
echo "  2. Test camera service manually:"
echo "     cd camera && python camera_service.py"
echo
echo "  3. Or use the launch script:"
echo "     ./scripts/start-development.sh"

echo
print_status "🔧 Troubleshooting:"
echo "  • If camera doesn't work, check /boot/config.txt for:"
echo "    camera_auto_detect=1  (or dtoverlay=imx500 for IMX500 sensor)"
echo "  • Ensure user is in video group:"
echo "    sudo usermod -aG video \$USER && newgrp video"
echo "  • Reboot after hardware configuration changes"

echo
print_status "📍 Environment details:"
echo "  Virtual env: $VENV_PATH"
echo "  Activation: source $ACTIVATE_SCRIPT"
echo "  Python path: Auto-configured for coordinate_recorder module"
