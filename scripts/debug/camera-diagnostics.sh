#!/bin/bash

# Integrated Camera Diagnostics and Fix Script
# カメラ関連診断・修復統合スクリプト
#
# Usage:
#   ./scripts/debug/camera-diagnostics.sh [OPTIONS]
#
# Options:
#   --comprehensive : 包括的診断（詳細ハードウェア・ソフトウェアチェック）
#   --startup      : 起動時診断（依存関係・環境変数チェック）
#   --production   : 本番環境診断（サービス状態・ログ確認）
#   --fix          : 修復処理（プロセス停止・サービス再起動）
#   --all          : 全ての診断を実行（comprehensive + startup + production）
#   --help         : このヘルプを表示

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "\n${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}🎯 $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
}

print_section() {
    echo -e "\n${BLUE}📋 $1${NC}"
    echo -e "${BLUE}$(printf '─%.0s' $(seq 1 ${#1}))${NC}"
}

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✅]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[⚠️ ]${NC} $1"
}

print_error() {
    echo -e "${RED}[❌]${NC} $1"
}

# Helper function to test URL connectivity
test_url() {
    local url=$1
    local timeout=${2:-3}

    if command -v curl > /dev/null 2>&1; then
        if curl -s --max-time $timeout "$url" > /dev/null 2>&1; then
            return 0
        else
            return 1
        fi
    else
        # Fallback to wget
        if wget -q --timeout=$timeout --tries=1 -O /dev/null "$url" 2>/dev/null; then
            return 0
        else
            return 1
        fi
    fi
}

# Function to check if user is in required groups
check_user_groups() {
    local user=$(whoami)
    local groups_output=$(groups)

    if echo "$groups_output" | grep -E "(video|camera)" > /dev/null; then
        print_success "User $user is in video/camera groups"
        return 0
    else
        print_warning "User $user not in video/camera groups: $groups_output"
        return 1
    fi
}

# Function to get project root
get_project_root() {
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    echo "$(cd "$script_dir/../.." && pwd)"
}

# Comprehensive diagnostics (from debug-camera.sh)
comprehensive_diagnostics() {
    print_header "包括的診断 - Comprehensive Diagnostics"

    echo "Date: $(date)"
    echo "Hostname: $(hostname)"
    echo "User: $(whoami)"
    echo

    print_section "1. Libcamera Devices Check"
    if command -v libcamera-hello &> /dev/null; then
        libcamera-hello --list-cameras 2>&1
    else
        print_warning "libcamera-hello not found. Installing may be required:"
        echo "  sudo apt install -y libcamera-apps"
    fi

    print_section "2. Video Devices Check"
    ls -la /dev/video* 2>&1 || print_warning "No video devices found"

    print_section "3. User Permissions Check"
    echo "Current user groups: $(groups)"
    check_user_groups

    print_section "4. System Camera Modules Check"
    echo "Loaded kernel modules:"
    lsmod | grep -E "(bcm2835|camera|imx|v4l2)" || print_warning "No camera modules found"

    print_section "5. DTOverlay Configuration Check"
    local config_files=("/boot/config.txt" "/boot/firmware/config.txt")
    local found_config=false

    for config_file in "${config_files[@]}"; do
        if [ -f "$config_file" ]; then
            echo "Camera-related dtoverlay settings in $config_file:"
            grep -E "(camera|imx)" "$config_file" || echo "  No camera overlays found"
            found_config=true
            break
        fi
    done

    if [ "$found_config" = false ]; then
        print_warning "config.txt not found in /boot or /boot/firmware"
    fi

    print_section "6. Python Environment Check"
    echo "Python version: $(python3 --version)"
    echo "Python path: $(which python3)"

    print_section "7. Picamera2 Installation Check"
    python3 -c "
try:
    import picamera2
    print(f'✅ Picamera2 version: {picamera2.__version__}')
    from picamera2 import Picamera2
    print('✅ Picamera2 can be imported')
except ImportError as e:
    print(f'❌ Picamera2 import error: {e}')
except Exception as e:
    print(f'❌ Unexpected error: {e}')
"

    print_section "8. Environment Variables Check"
    local env_vars=("CAMERA_MODE" "API_URL" "PHOTOS_DIR" "CAMERA_PORT" "BACKEND_API_URL")
    for var in "${env_vars[@]}"; do
        if [ -n "${!var}" ]; then
            print_success "$var=${!var}"
        else
            print_warning "$var not set"
        fi
    done

    print_section "9. Camera Detection Test"
    python3 - << 'EOF'
import sys
import os

# Force hardware mode for this test
os.environ['CAMERA_MODE'] = 'hardware'

try:
    from picamera2 import Picamera2

    # List available cameras
    print("Checking for available cameras...")
    cameras = Picamera2.global_camera_info()
    if cameras:
        print(f"✅ Found {len(cameras)} camera(s):")
        for i, cam in enumerate(cameras):
            print(f"  Camera {i}: {cam}")
    else:
        print("❌ No cameras detected by Picamera2")

    # Try to create instance
    print("\nAttempting to create Picamera2 instance...")
    picam2 = Picamera2()
    print("✅ Picamera2 instance created successfully")

    # Get camera properties
    props = picam2.camera_properties
    print(f"\n✅ Camera Properties:")
    print(f"  Model: {props.get('Model', 'Unknown')}")
    print(f"  Sensor Resolution: {props.get('PixelArraySize', 'Unknown')}")
    print(f"  Location: {props.get('Location', 'Unknown')}")
    print(f"  Rotation: {props.get('Rotation', 'Unknown')}")

    # List available sensor modes
    sensor_modes = picam2.sensor_modes
    print(f"\n✅ Available sensor modes: {len(sensor_modes)}")
    for i, mode in enumerate(sensor_modes[:3]):  # Show first 3 modes
        print(f"  Mode {i}: {mode}")

    picam2.close()
    print("\n✅ Camera closed successfully")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("  Try: sudo apt install -y python3-picamera2")
except RuntimeError as e:
    print(f"❌ Runtime error: {e}")
    if "No cameras available" in str(e):
        print("\n  Possible causes:")
        print("  - Camera not connected properly")
        print("  - Camera interface not enabled (run 'sudo raspi-config')")
        print("  - Incompatible camera module")
        print("  - Need to add dtoverlay=imx500 to /boot/config.txt")
except Exception as e:
    print(f"❌ Unexpected error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
EOF

    print_section "10. Service Status Check"
    if systemctl is-active --quiet coordinate-camera.service 2>/dev/null; then
        print_success "Camera service is running"
        echo "Service environment:"
        systemctl show coordinate-camera.service 2>/dev/null | grep -E "Environment=|ExecStart=|WorkingDirectory=" || true
        echo
        echo "Recent logs:"
        sudo journalctl -u coordinate-camera.service -n 30 --no-pager 2>/dev/null || true
    else
        print_warning "Camera service is not running"
        echo "Last logs:"
        sudo journalctl -u coordinate-camera.service -n 30 --no-pager 2>/dev/null || true
    fi

    print_section "Diagnostic Summary"
    echo "If camera is not working, check:"
    echo "1. Camera cable connection (ribbon cable firmly seated on both ends)"
    echo "2. Camera enabled in raspi-config (Interface Options > Camera)"
    echo "3. User in 'video' group (sudo usermod -aG video \$USER)"
    echo "4. Correct dtoverlay in /boot/config.txt:"
    echo "   - For IMX500: dtoverlay=imx500"
    echo "   - For standard camera: camera_auto_detect=1"
    echo "5. Environment variable CAMERA_MODE=hardware is set"
    echo "6. Reboot after any configuration changes"
}

# Startup diagnostics (from camera-startup-check.sh)
startup_diagnostics() {
    print_header "起動診断 - Startup Diagnostics"

    local PROJECT_ROOT=$(get_project_root)
    cd "$PROJECT_ROOT"

    print_section "Python Environment Check"
    python3 --version || print_error "Python3 not found"

    # Check virtual environment
    if [ -n "$VIRTUAL_ENV" ]; then
        print_success "Virtual environment active: $VIRTUAL_ENV"
    elif [ -f "venv/bin/activate" ]; then
        print_warning "Virtual environment available but not active"
        echo "Activating virtual environment..."
        source venv/bin/activate
        print_success "Virtual environment activated"
    else
        print_warning "No virtual environment found"
    fi

    print_section "Python Dependencies Check"
    local dependencies=("fastapi" "uvicorn" "httpx" "opencv-python" "numpy" "pillow" "requests")
    local missing_deps=()

    for dep in "${dependencies[@]}"; do
        if python3 -c "import ${dep//-/_}" 2>/dev/null; then
            print_success "$dep"
        else
            print_error "$dep"
            missing_deps+=("$dep")
        fi
    done

    print_section "Raspberry Pi Dependencies Check"
    if python3 -c "import picamera2" 2>/dev/null; then
        print_success "picamera2 (Raspberry Pi camera support)"
    else
        print_warning "picamera2 not available (will use USB/simulation mode)"
    fi

    if python3 -c "import libcamera" 2>/dev/null; then
        print_success "libcamera"
    else
        print_warning "libcamera not available"
    fi

    print_section "Environment Variables Check"
    local important_vars=("CAMERA_PORT" "CAMERA_MODE" "API_URL" "BACKEND_API_URL" "PHOTOS_DIR")

    for var in "${important_vars[@]}"; do
        if [ -n "${!var}" ]; then
            print_success "$var=${!var}"
        else
            print_warning "$var not set"
        fi
    done

    print_section "Port Availability Check"
    local CAMERA_PORT=${CAMERA_PORT:-8001}
    if lsof -i :$CAMERA_PORT > /dev/null 2>&1; then
        print_error "Port $CAMERA_PORT is busy"
        echo "Processes using port $CAMERA_PORT:"
        lsof -i :$CAMERA_PORT
    else
        print_success "Port $CAMERA_PORT is available"
    fi

    print_section "File Permissions Check"
    local camera_script="$PROJECT_ROOT/camera/camera_service.py"
    if [ -f "$camera_script" ]; then
        if [ -r "$camera_script" ]; then
            print_success "Camera service script readable"
        else
            print_error "Camera service script not readable"
        fi

        if [ -x "$camera_script" ]; then
            print_success "Camera service script executable"
        else
            print_warning "Camera service script not executable (but can be run with python)"
        fi
    else
        print_error "Camera service script not found: $camera_script"
    fi

    print_section "Basic Import Test"
    cd "$PROJECT_ROOT/camera"

    # Create temporary test file
    local temp_file=$(mktemp)
    trap 'rm -f "$temp_file"' EXIT

    cat > "$temp_file" << 'EOF'
#!/usr/bin/env python3
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def test_import(module_name, description):
    try:
        __import__(module_name)
        print(f"✅ {description}")
        return True
    except ImportError as e:
        print(f"❌ {description}: {e}")
        return False

print("Testing critical imports...")
success = True

# Test core dependencies
success &= test_import("fastapi", "FastAPI")
success &= test_import("uvicorn", "Uvicorn")
success &= test_import("cv2", "OpenCV")
success &= test_import("numpy", "NumPy")
success &= test_import("httpx", "HTTPX")

# Test optional dependencies
test_import("picamera2", "Picamera2 (optional)")
test_import("libcamera", "Libcamera (optional)")

# Test coordinate_recorder imports
try:
    from coordinate_recorder.edge_filter import EdgeFilter
    print("✅ EdgeFilter import")
except ImportError as e:
    print(f"❌ EdgeFilter import: {e}")
    success = False

if success:
    print("\n🎉 All critical imports successful!")
    sys.exit(0)
else:
    print("\n💥 Some critical imports failed!")
    sys.exit(1)
EOF

    if python3 "$temp_file"; then
        print_success "Import test passed"
        local import_success=true
    else
        print_error "Import test failed"
        local import_success=false
    fi

    if [ "$import_success" = true ]; then
        print_section "Camera Service Startup Test"
        echo "Testing camera service startup (will exit after initialization)..."

        # Set test mode to prevent actual server startup
        export CAMERA_MODE="simulation"
        export CAMERA_PORT="18001"  # Use a different port for testing

        timeout 10s python3 -c "
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Load environment
def load_env_file():
    env_file = '../.env'
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key and value:
                        os.environ[key] = value

load_env_file()

# Test camera service initialization
from camera_service import CameraService
print('Testing camera service initialization...')
service = CameraService()
print('✅ Camera service initialized successfully!')
print(f'Camera mode: {service.camera_mode}')
print(f'API URL: {service.api_url}')
print(f'Photos dir: {service.photos_dir}')
" && print_success "Camera service startup test passed" || print_error "Camera service startup test failed"
    else
        print_warning "Skipping startup test due to import failures"
    fi

    # Summary
    print_section "Startup Diagnostic Summary"
    if [ ${#missing_deps[@]} -eq 0 ]; then
        print_success "All core dependencies available"
    else
        print_error "Missing dependencies: ${missing_deps[*]}"
        echo "To install missing dependencies:"
        echo "  pip install ${missing_deps[*]}"
    fi

    echo
    echo "💡 Next Steps:"
    echo "1. If dependencies are missing, install them with pip"
    echo "2. Check the actual camera service logs:"
    echo "   tail -50 $PROJECT_ROOT/logs/camera*service.log"
    echo "3. Try starting the camera service manually:"
    echo "   cd $PROJECT_ROOT/camera && python3 camera_service.py"
    echo "4. For Raspberry Pi, ensure picamera2 is installed:"
    echo "   sudo apt update && sudo apt install -y python3-picamera2"

    cd "$PROJECT_ROOT"
}

# Production diagnostics (from diagnose-production-camera.sh)
production_diagnostics() {
    print_header "本番環境診断 - Production Diagnostics"

    print_section "System Information"
    echo "Hostname: $(hostname)"
    echo "Date: $(date)"
    echo "User: $(whoami)"
    echo "Working Directory: $(pwd)"
    echo ""

    print_section "Service Status Check"
    echo "Checking coordinate-camera.service status..."
    if systemctl is-active coordinate-camera.service > /dev/null 2>&1; then
        print_success "systemd service is active"
    else
        print_error "systemd service is NOT active"
        echo "Status: $(systemctl is-active coordinate-camera.service)"
        echo "Enabled: $(systemctl is-enabled coordinate-camera.service)"
    fi

    print_section "Port Availability Check"
    for port in 8000 8001 3000; do
        if lsof -i :$port > /dev/null 2>&1; then
            local pids=$(lsof -ti :$port)
            print_warning "Port $port is occupied by PID(s): $pids"
            ps -p $pids -o pid,ppid,cmd 2>/dev/null || true
        else
            print_success "Port $port is available"
        fi
    done

    print_section "Camera Hardware Check"
    if [ -d "/dev" ]; then
        local video_devices=$(ls /dev/video* 2>/dev/null || echo "none")
        if [ "$video_devices" != "none" ]; then
            print_success "Video devices found: $video_devices"
        else
            print_warning "No video devices found"
        fi
    fi

    # Check for Raspberry Pi camera
    if [ -f "/opt/vc/bin/vcgencmd" ]; then
        local camera_detected=$(/opt/vc/bin/vcgencmd get_camera 2>/dev/null || echo "unknown")
        print_status "Raspberry Pi camera status: $camera_detected"
    fi

    print_section "Python Environment Check"
    which python3
    python3 --version
    echo "PYTHONPATH: ${PYTHONPATH:-'not set'}"

    # Check for required modules
    local modules=("cv2" "picamera2" "fastapi" "uvicorn" "numpy")
    for module in "${modules[@]}"; do
        if python3 -c "import $module" 2>/dev/null; then
            print_success "Module $module is available"
        else
            print_error "Module $module is NOT available"
        fi
    done

    print_section "File System Check"
    local camera_service_path="/home/pi/coordinate-recorder/camera/camera_service.py"
    if [ -f "$camera_service_path" ]; then
        print_success "Camera service file exists: $camera_service_path"
    else
        print_error "Camera service file NOT found: $camera_service_path"
    fi

    local start_script_path="/home/pi/coordinate-recorder/scripts/launch/services/start-camera.sh"
    if [ -f "$start_script_path" ]; then
        print_success "Start script exists: $start_script_path"
        if [ -x "$start_script_path" ]; then
            print_success "Start script is executable"
        else
            print_warning "Start script is not executable"
        fi
    else
        print_error "Start script NOT found: $start_script_path"
    fi

    print_section "Environment Variables Check"
    echo "CAMERA_MODE: ${CAMERA_MODE:-'not set'}"
    echo "API_URL: ${API_URL:-'not set'}"
    echo "PHOTOS_DIR: ${PHOTOS_DIR:-'not set'}"
    echo "VITE_CAMERA_URL: ${VITE_CAMERA_URL:-'not set'}"

    # Check .env file
    local env_file="/home/pi/coordinate-recorder/.env"
    if [ -f "$env_file" ]; then
        print_success ".env file exists: $env_file"
        echo "Camera-related variables in .env:"
        grep -E "(CAMERA|STREAM|MODE)" "$env_file" || echo "No camera variables found"
    else
        print_warning ".env file not found: $env_file"
    fi

    print_section "Recent Logs Check"
    if command -v journalctl > /dev/null 2>&1; then
        echo "Recent systemd logs for coordinate-camera:"
        journalctl -u coordinate-camera.service --lines=10 --no-pager 2>/dev/null || true
    else
        print_warning "journalctl not available"
    fi

    # Check for log files
    local log_files=(
        "/home/pi/coordinate-recorder/logs/camera-service.log"
        "/home/pi/coordinate-recorder/camera/camera.log"
        "/tmp/camera-service.log"
    )

    for log_file in "${log_files[@]}"; do
        if [ -f "$log_file" ]; then
            print_success "Log file found: $log_file"
            echo "Last 5 lines:"
            tail -5 "$log_file" 2>/dev/null || true
            echo ""
        fi
    done

    print_section "Suggested Recovery Actions"
    echo
    echo "1. Restart systemd service:"
    echo "   sudo systemctl restart coordinate-camera.service"
    echo
    echo "2. Check detailed service status:"
    echo "   sudo systemctl status coordinate-camera.service"
    echo
    echo "3. View real-time logs:"
    echo "   sudo journalctl -u coordinate-camera.service -f"
    echo
    echo "4. Manual camera service start (for debugging):"
    echo "   cd /home/pi/coordinate-recorder"
    echo "   CAMERA_MODE=hardware python3 camera/camera_service.py"
    echo
    echo "5. If Picamera2 fails, try simulation mode:"
    echo "   CAMERA_MODE=simulation python3 camera/camera_service.py"
    echo
    echo "6. Check network connectivity:"
    echo "   curl http://localhost:8000/health"
    echo "   curl http://localhost:8001/health"
}

# Fix procedures (from fix-production-camera.sh)
fix_procedures() {
    print_header "修復処理 - Fix Procedures"

    print_section "Stopping conflicting processes on port 8001"
    if command -v lsof > /dev/null 2>&1; then
        local pids=$(lsof -ti :8001 2>/dev/null || true)
        if [ -n "$pids" ]; then
            print_warning "Found processes on port 8001: $pids"
            echo "$pids" | xargs kill -TERM 2>/dev/null || true
            sleep 2
            # Force kill if still running
            local remaining_pids=$(lsof -ti :8001 2>/dev/null || true)
            if [ -n "$remaining_pids" ]; then
                echo "$remaining_pids" | xargs kill -KILL 2>/dev/null || true
            fi
            print_success "Cleared port 8001"
        else
            print_success "Port 8001 is already free"
        fi
    else
        print_warning "lsof not available, skipping port cleanup"
    fi

    print_section "Testing API service connectivity"
    if test_url "http://localhost:8000/health"; then
        print_success "API service is responding"
    else
        print_error "API service is not responding"
        print_status "You may need to start the API service first"
    fi

    print_section "Restarting coordinate-camera.service"
    if command -v systemctl > /dev/null 2>&1; then
        if systemctl restart coordinate-camera.service 2>/dev/null; then
            print_success "systemd service restarted"
            sleep 3

            # Check if service is now active
            if systemctl is-active coordinate-camera.service > /dev/null 2>&1; then
                print_success "systemd service is now active"
            else
                print_warning "systemd service failed to start"
            fi
        else
            print_error "Failed to restart systemd service (may need sudo)"
        fi
    else
        print_warning "systemctl not available"
    fi

    print_section "Testing camera service"
    for attempt in {1..5}; do
        print_status "Attempt $attempt/5: Testing http://localhost:8001"

        if test_url "http://localhost:8001"; then
            print_success "Camera service is responding!"
            break
        else
            if [ $attempt -eq 5 ]; then
                print_error "Camera service still not responding after 5 attempts"
            else
                print_warning "Camera service not responding, waiting 3 seconds..."
                sleep 3
            fi
        fi
    done

    print_section "Testing stream endpoint"
    if test_url "http://localhost:8001/stream"; then
        print_success "Stream endpoint is accessible"
    else
        print_warning "Stream endpoint is not accessible"
    fi

    # Manual start fallback (if systemd failed)
    if ! test_url "http://localhost:8001"; then
        print_section "Attempting manual camera service start"

        # Set up environment
        export CAMERA_MODE=hardware
        export PYTHONPATH="/home/pi/coordinate-recorder/src:$PYTHONPATH"

        cd /home/pi/coordinate-recorder/camera

        print_status "Starting camera service manually..."
        # Try hardware mode first
        nohup python3 camera_service.py > /tmp/camera-manual.log 2>&1 &
        local manual_pid=$!

        sleep 5

        if ps -p $manual_pid > /dev/null 2>&1; then
            print_success "Manual camera service started (PID: $manual_pid)"

            # Test again
            if test_url "http://localhost:8001"; then
                print_success "Manual camera service is responding!"
            else
                print_warning "Manual service started but not responding to HTTP"
            fi
        else
            print_error "Manual camera service failed to start"
            print_status "Trying simulation mode..."

            # Try simulation mode as fallback
            CAMERA_MODE=simulation nohup python3 camera_service.py > /tmp/camera-simulation.log 2>&1 &
            local sim_pid=$!

            sleep 3

            if ps -p $sim_pid > /dev/null 2>&1; then
                print_success "Simulation camera service started (PID: $sim_pid)"
            else
                print_error "Both hardware and simulation modes failed"
            fi
        fi
    fi

    print_section "Final connectivity test"
    echo
    echo "Testing key endpoints:"

    local endpoints=(
        "http://localhost:8000/health:API Health"
        "http://localhost:8001:Camera Service"
        "http://localhost:8001/stream:Camera Stream"
    )

    for endpoint_info in "${endpoints[@]}"; do
        IFS=':' read -r url description <<< "$endpoint_info"
        if test_url "$url"; then
            print_success "$description: ✅ OK"
        else
            print_error "$description: ❌ FAIL"
        fi
    done

    echo
    print_status "Fix attempt complete!"
    echo
    echo "If camera service is still not working:"
    echo "1. Check logs: tail -f /tmp/camera-manual.log"
    echo "2. Check hardware: ls /dev/video*"
    echo "3. Try simulation mode: CAMERA_MODE=simulation python3 camera_service.py"
    echo "4. Check systemd logs: journalctl -u coordinate-camera.service -f"
}

# Show help
show_help() {
    echo -e "${CYAN}Camera Diagnostics and Fix Script${NC}"
    echo -e "${CYAN}===================================${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --comprehensive : 包括的診断（詳細ハードウェア・ソフトウェアチェック）"
    echo "  --startup       : 起動時診断（依存関係・環境変数チェック）"
    echo "  --production    : 本番環境診断（サービス状態・ログ確認）"
    echo "  --fix           : 修復処理（プロセス停止・サービス再起動）"
    echo "  --all           : 全ての診断を実行（comprehensive + startup + production）"
    echo "  --help          : このヘルプを表示"
    echo ""
    echo "Examples:"
    echo "  $0 --comprehensive  # 詳細なハードウェア・ソフトウェア診断を実行"
    echo "  $0 --startup        # 起動時の依存関係チェックを実行"
    echo "  $0 --production     # 本番環境でのサービス状態確認"
    echo "  $0 --fix            # カメラサービスの修復処理を実行"
    echo "  $0 --all            # 全ての診断を順次実行"
    echo ""
    echo "機能説明："
    echo "  comprehensive : libcamera、Picamera2、カメラハードウェアの詳細チェック"
    echo "  startup       : Python依存関係、環境変数、ポート可用性のチェック"
    echo "  production    : systemdサービス、ログ、本番環境特有の問題診断"
    echo "  fix           : プロセス停止、サービス再起動、手動起動の自動実行"
}

# Main execution
main() {
    local mode=""
    local run_comprehensive=false
    local run_startup=false
    local run_production=false
    local run_fix=false

    # Parse arguments
    for arg in "$@"; do
        case $arg in
            --comprehensive)
                run_comprehensive=true
                ;;
            --startup)
                run_startup=true
                ;;
            --production)
                run_production=true
                ;;
            --fix)
                run_fix=true
                ;;
            --all)
                run_comprehensive=true
                run_startup=true
                run_production=true
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $arg${NC}"
                echo "Use --help to see available options"
                exit 1
                ;;
        esac
    done

    # If no arguments provided, show help
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi

    print_header "カメラ統合診断・修復ツール - Camera Integrated Diagnostics & Fix Tool"
    echo "Started at: $(date)"

    # Execute selected diagnostics
    if [ "$run_comprehensive" = true ]; then
        comprehensive_diagnostics
    fi

    if [ "$run_startup" = true ]; then
        startup_diagnostics
    fi

    if [ "$run_production" = true ]; then
        production_diagnostics
    fi

    if [ "$run_fix" = true ]; then
        fix_procedures
    fi

    echo -e "\n${CYAN}診断完了 - Diagnostics Complete${NC}"
    echo "Finished at: $(date)"
}

# Run main function with all arguments
main "$@"
