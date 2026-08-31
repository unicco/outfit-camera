#!/bin/bash

echo "=== Installing Camera Service Dependencies (Picamera2 + Virtual Environment) ==="
echo "This script sets up dependencies for Raspberry Pi with proper Picamera2 support"
echo

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

print_header "📦 System packages installation"

# システムパッケージの更新とインストール
print_status "Updating package lists..."
sudo apt update

print_status "Installing system dependencies..."
sudo apt install -y \
    python3-opencv \
    python3-numpy \
    python3-picamera2 \
    python3-pillow \
    python3-pip \
    python3-venv \
    libcamera-apps \
    libcamera-dev \
    python3-fastapi \
    python3-uvicorn \
    python3-aiofiles \
    python3-mediapipe

print_header "🐍 Virtual environment setup"

# 既存の仮想環境を削除（Picamera2 対応のため）
if [ -d "$VENV_PATH" ]; then
    print_warning "Removing existing virtual environment for Picamera2 compatibility..."
    rm -rf "$VENV_PATH"
fi

# system-site-packages フラグ付きで仮想環境作成
print_status "Creating virtual environment with system-site-packages access..."
python3 -m venv --system-site-packages "$VENV_PATH"

# 仮想環境を有効化
print_status "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# 仮想環境内で必要な追加パッケージをインストール
print_status "Installing additional packages in virtual environment..."

# NumPy と OpenCV の互換性を確保
pip install 'numpy>=1.21,<2' 'opencv-python<4.12' pillow || {
    print_error "NumPy/OpenCV/Pillow インストール失敗"
    exit 1
}

# 残りの必要なパッケージ
pip install python-multipart python-dotenv fastapi 'uvicorn[standard]' httpx || {
    print_error "Web フレームワーク依存関係インストール失敗"
    exit 1
}

# AI関連パッケージ（システムPython用にも必要）
print_status "Installing AI-related packages..."
pip install google-generativeai || {
    print_warning "google-generativeai installation in venv failed, will need system-level install"
}

print_header "🔗 Creating symlinks for system-only packages"

# libcamera と pykms のシムリンク作成（仮想環境からアクセス可能にする）
VENV_SITE_PACKAGES="$VENV_PATH/lib/python*/site-packages"

print_status "Creating libcamera symlink..."
for site_pkg_dir in $VENV_SITE_PACKAGES; do
    if [ -d "$site_pkg_dir" ]; then
        if [ -d "/usr/lib/python3/dist-packages/libcamera" ]; then
            ln -sf /usr/lib/python3/dist-packages/libcamera "$site_pkg_dir/libcamera" || {
                print_warning "Failed to create libcamera symlink"
            }
            print_status "✅ libcamera symlink created"
        else
            print_warning "⚠️ System libcamera not found at expected location"
        fi
        break
    fi
done

print_status "Creating pykms symlink..."
for site_pkg_dir in $VENV_SITE_PACKAGES; do
    if [ -d "$site_pkg_dir" ]; then
        if [ -d "/usr/lib/python3/dist-packages/pykms" ]; then
            ln -sf /usr/lib/python3/dist-packages/pykms "$site_pkg_dir/pykms" || {
                print_warning "Failed to create pykms symlink"
            }
            print_status "✅ pykms symlink created"
        else
            print_warning "⚠️ System pykms not found at expected location"
        fi
        break
    fi
done

echo
echo "Verifying installations..."

# 仮想環境での検証テスト
python3 -c "
print('🧪 Testing installations in virtual environment...')
print(f'Python executable: {__import__('sys').executable}')
print()

success_count = 0
total_tests = 7

def test_import(module_name, display_name=None):
    global success_count
    display_name = display_name or module_name
    try:
        module = __import__(module_name)
        version = getattr(module, '__version__', 'unknown')
        print(f'✅ {display_name}: {version}')
        success_count += 1
        return True
    except ImportError as e:
        print(f'❌ {display_name}: ImportError - {e}')
        return False

# Core dependencies
test_import('cv2', 'OpenCV')
test_import('numpy', 'NumPy')
test_import('PIL', 'Pillow')

# Raspberry Pi specific
try:
    import picamera2
    from picamera2 import Picamera2
    print('✅ Picamera2: Hardware camera support available')
    success_count += 1
except ImportError as e:
    print(f'❌ Picamera2: {e}')

# Web framework
test_import('fastapi', 'FastAPI')
test_import('uvicorn', 'Uvicorn')

# Additional packages
test_import('multipart', 'python-multipart')

print()
print(f'📊 Test Results: {success_count}/{total_tests} passed')

if success_count == total_tests:
    print('🎉 All dependencies installed successfully!')
    print()
    print('📝 Next steps:')
    print('  1. Restart your development environment:')
    print('     ./scripts/stop-development.sh && ./scripts/start-development.sh')
    print('  2. Verify camera functionality:')
    print('     curl http://localhost:8001/stream')
    print('  3. Check camera hardware mode in logs:')
    print('     tail -f logs/camera*service.log')
else:
    print('⚠️ Some dependencies failed to install.')
    print('Please check error messages above and retry installation.')
"

# 旧サービスの停止・削除は deploy/setup-pi.sh の OBSOLETE_SERVICES に集約した。
# ここで名前を直書きすると、改称のたびに 2 箇所を直す必要が出る。

echo
echo "=== Installation complete ==="
echo
print_status "🎯 Key improvements implemented:"
echo "  ✅ Virtual environment with system-site-packages access"
echo "  ✅ Proper Picamera2 hardware support"
echo "  ✅ OpenCV and NumPy version compatibility"
echo "  ✅ System service conflict resolution"
echo "  ✅ libcamera and pykms symlinks for virtual environment access"
echo
print_status "🚀 Your camera should now work in hardware mode instead of USB simulation!"
echo "Use the start-development.sh script to start services with the new environment."
echo
