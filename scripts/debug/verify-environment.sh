#!/bin/bash

# Coordinate Recorder - Environment Verification Script
# This script verifies that the system is properly configured and all dependencies are met

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$HOME/coordinate-recorder"

# Color output functions
print_header() {
    echo -e "\n\033[1;36m========================================\033[0m"
    echo -e "\033[1;36m$1\033[0m"
    echo -e "\033[1;36m========================================\033[0m"
}

print_check() {
    echo -e "\n\033[1;34m[CHECK]\033[0m $1"
}

print_success() {
    echo -e "\033[1;32m✓ PASS\033[0m $1"
}

print_warning() {
    echo -e "\033[1;33m⚠ WARN\033[0m $1"
}

print_error() {
    echo -e "\033[1;31m✗ FAIL\033[0m $1"
}

print_info() {
    echo -e "\033[0;37m  → $1\033[0m"
}

# Global counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Check result tracking
check_result() {
    local status=$1
    local message=$2

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    case $status in
        "pass")
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
            print_success "$message"
            ;;
        "warn")
            WARNING_CHECKS=$((WARNING_CHECKS + 1))
            print_warning "$message"
            ;;
        "fail")
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
            print_error "$message"
            ;;
    esac
}

# Hardware verification
verify_hardware() {
    print_header "HARDWARE VERIFICATION"

    print_check "Checking Raspberry Pi hardware"
    if grep -q "Raspberry Pi" /proc/cpuinfo; then
        local model=$(grep "Model" /proc/cpuinfo | cut -d: -f2 | xargs)
        check_result "pass" "Running on $model"

        if grep -q "BCM2712" /proc/cpuinfo; then
            check_result "pass" "Raspberry Pi 5 detected (optimal performance)"
        else
            check_result "warn" "Not running on Raspberry Pi 5 (may have reduced performance)"
        fi
    else
        check_result "fail" "Not running on Raspberry Pi hardware"
    fi

    print_check "Checking memory"
    local memory_mb=$(free -m | awk '/^Mem:/{print $2}')
    print_info "Total memory: ${memory_mb}MB"

    if [ "$memory_mb" -ge 7000 ]; then
        check_result "pass" "8GB+ RAM available (optimal)"
    elif [ "$memory_mb" -ge 3000 ]; then
        check_result "pass" "4GB+ RAM available (sufficient)"
    else
        check_result "warn" "Less than 4GB RAM (may cause performance issues)"
    fi

    print_check "Checking storage"
    local storage_gb=$(df -BG / | awk 'NR==2 {print $2}' | sed 's/G//')
    local available_gb=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
    print_info "Total storage: ${storage_gb}GB, Available: ${available_gb}GB"

    if [ "$available_gb" -ge 10 ]; then
        check_result "pass" "Sufficient storage space available"
    elif [ "$available_gb" -ge 5 ]; then
        check_result "warn" "Low storage space (consider cleanup)"
    else
        check_result "fail" "Critical: Less than 5GB storage available"
    fi

    print_check "Checking CPU temperature"
    if command -v vcgencmd &> /dev/null; then
        local temp=$(vcgencmd measure_temp | cut -d= -f2 | cut -d\' -f1)
        print_info "Current temperature: ${temp}°C"

        if (( $(echo "$temp < 70" | bc -l) )); then
            check_result "pass" "CPU temperature normal"
        elif (( $(echo "$temp < 80" | bc -l) )); then
            check_result "warn" "CPU temperature elevated (consider cooling)"
        else
            check_result "fail" "CPU temperature critical (check cooling)"
        fi
    else
        check_result "warn" "Cannot check CPU temperature (vcgencmd not available)"
    fi
}

# Camera verification
verify_camera() {
    print_header "CAMERA VERIFICATION"

    print_check "Checking libcamera tools"
    if command -v libcamera-hello &> /dev/null; then
        check_result "pass" "libcamera tools available"

        print_check "Detecting cameras"
        local camera_output=$(libcamera-hello --list-cameras 2>/dev/null || echo "")

        if echo "$camera_output" | grep -q "imx500"; then
            check_result "pass" "Sony IMX500 camera detected"
            print_info "Camera: $(echo "$camera_output" | grep imx500 | head -1)"
        elif echo "$camera_output" | grep -q "Available cameras"; then
            check_result "warn" "Camera detected but not IMX500"
            print_info "Camera: $(echo "$camera_output" | grep -v "Available cameras" | head -1)"
        else
            check_result "fail" "No cameras detected"
            print_info "Make sure camera is properly connected and enabled"
        fi
    else
        check_result "fail" "libcamera tools not found"
        print_info "Install with: sudo apt install libcamera-tools"
    fi

    print_check "Checking camera configuration"
    if grep -q "camera_auto_detect=1" /boot/firmware/config.txt; then
        check_result "pass" "Camera auto-detection enabled"
    else
        check_result "warn" "Camera auto-detection not explicitly enabled"
        print_info "Add 'camera_auto_detect=1' to /boot/firmware/config.txt"
    fi

    print_check "Checking video devices"
    if ls /dev/video* &> /dev/null; then
        local video_count=$(ls /dev/video* | wc -l)
        check_result "pass" "$video_count video device(s) found"
        print_info "Devices: $(ls /dev/video* | tr '\n' ' ')"
    else
        check_result "warn" "No video devices found"
    fi
}

# System dependencies verification
verify_system_dependencies() {
    print_header "SYSTEM DEPENDENCIES"

    local packages=("python3" "python3-pip" "python3-picamera2")

    for package in "${packages[@]}"; do
        print_check "Checking $package"
        if dpkg -l | grep -q "^ii.*$package"; then
            local version=$(dpkg -l | grep "^ii.*$package" | awk '{print $3}' | cut -d: -f1)
            check_result "pass" "$package installed ($version)"
        else
            check_result "fail" "$package not installed"
            print_info "Install with: sudo apt install $package"
        fi
    done


    print_check "Checking Python libraries"
    if python3 -c "from picamera2 import Picamera2" 2>/dev/null; then
        check_result "pass" "Picamera2 library available"
    else
        check_result "fail" "Picamera2 library not available"
        print_info "Install with: sudo apt install python3-picamera2"
    fi
}

# User permissions verification
verify_permissions() {
    print_header "USER PERMISSIONS"

    local current_user=$(whoami)
    print_info "Current user: $current_user"

    print_check "Checking video group membership"
    if groups "$current_user" | grep -q video; then
        check_result "pass" "User in video group (camera access)"
    else
        check_result "fail" "User not in video group"
        print_info "Add with: sudo usermod -aG video $current_user"
    fi


    print_check "Checking project directory permissions"
    if [ -d "$PROJECT_DIR" ]; then
        if [ -w "$PROJECT_DIR" ]; then
            check_result "pass" "Project directory writable"
        else
            check_result "fail" "Project directory not writable"
        fi
    else
        check_result "warn" "Project directory does not exist"
        print_info "Clone the repo to ~/coordinate-recorder, then run: bash deploy/setup-pi.sh"
    fi
}

# Service verification
verify_services() {
    print_header "SERVICE VERIFICATION"

    print_check "Checking camera service"
    if systemctl is-active --quiet coordinate-camera.service; then
        check_result "pass" "Camera service running"

        # Test camera endpoint
        if curl -f -s http://localhost:8001/capture > /dev/null 2>&1; then
            check_result "pass" "Camera service responding"
        else
            check_result "warn" "Camera service not responding to requests"
        fi
    else
        check_result "fail" "Camera service not running"
        print_info "Start with: sudo systemctl start coordinate-camera.service"
    fi

    if [ -d "$PROJECT_DIR" ]; then
        cd "$PROJECT_DIR"

        print_check "Testing backend service"
        if curl -f -s http://localhost:8000/docs > /dev/null 2>&1; then
            check_result "pass" "Backend service responding"
        else
            check_result "fail" "Backend service not responding"
        fi

        print_check "Testing frontend service"
        if curl -f -s http://localhost:3000 > /dev/null 2>&1; then
            check_result "pass" "Frontend service responding"
        else
            check_result "fail" "Frontend service not responding"
        fi
    else
        check_result "warn" "Project directory not found, skipping service check"
    fi
}

# Network verification
verify_network() {
    print_header "NETWORK VERIFICATION"

    local ports=("3000" "8000" "8001")

    for port in "${ports[@]}"; do
        print_check "Checking port $port availability"
        if netstat -tuln | grep -q ":$port "; then
            local service=$(netstat -tulpn 2>/dev/null | grep ":$port " | awk '{print $7}' | cut -d/ -f2 | head -1)
            check_result "pass" "Port $port in use by $service"
        else
            check_result "warn" "Port $port not in use"
        fi
    done

    print_check "Checking internet connectivity"
    if ping -c 1 google.com > /dev/null 2>&1; then
        check_result "pass" "Internet connectivity available"
    else
        check_result "warn" "No internet connectivity (may affect package downloads)"
    fi

    print_check "Checking hostname resolution"
    local hostname=$(hostname)
    if ping -c 1 "$hostname.local" > /dev/null 2>&1; then
        check_result "pass" "Hostname $hostname.local resolves"
    else
        check_result "warn" "Hostname resolution may not work from other devices"
        print_info "Install avahi-daemon for .local domain support"
    fi
}

# Performance verification
verify_performance() {
    print_header "PERFORMANCE VERIFICATION"

    print_check "Checking system load"
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    print_info "Current load average: $load_avg"

    if (( $(echo "$load_avg < 1.0" | bc -l) )); then
        check_result "pass" "System load normal"
    elif (( $(echo "$load_avg < 2.0" | bc -l) )); then
        check_result "warn" "System load elevated"
    else
        check_result "fail" "System load high"
    fi

    print_check "Checking disk I/O"
    if command -v iostat &> /dev/null; then
        local io_wait=$(iostat 1 2 | tail -1 | awk '{print $4}')
        print_info "I/O wait: ${io_wait}%"

        if (( $(echo "$io_wait < 10" | bc -l) )); then
            check_result "pass" "Disk I/O normal"
        else
            check_result "warn" "Disk I/O may be bottleneck"
        fi
    else
        check_result "warn" "Cannot check disk I/O (install sysstat)"
    fi

    print_check "Checking memory usage"
    local mem_used=$(free | awk '/^Mem:/{printf "%.1f", $3/$2 * 100}')
    print_info "Memory usage: ${mem_used}%"

    if (( $(echo "$mem_used < 70" | bc -l) )); then
        check_result "pass" "Memory usage normal"
    elif (( $(echo "$mem_used < 85" | bc -l) )); then
        check_result "warn" "Memory usage elevated"
    else
        check_result "fail" "Memory usage critical"
    fi
}

# Generate summary report
generate_summary() {
    print_header "VERIFICATION SUMMARY"

    echo -e "\n\033[1;36mResults:\033[0m"
    echo -e "  Total checks: $TOTAL_CHECKS"
    echo -e "  \033[1;32mPassed: $PASSED_CHECKS\033[0m"
    echo -e "  \033[1;33mWarnings: $WARNING_CHECKS\033[0m"
    echo -e "  \033[1;31mFailed: $FAILED_CHECKS\033[0m"

    local pass_rate=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
    echo -e "\n\033[1;36mPass Rate: ${pass_rate}%\033[0m"

    if [ "$FAILED_CHECKS" -eq 0 ]; then
        if [ "$WARNING_CHECKS" -eq 0 ]; then
            echo -e "\n\033[1;32m🎉 EXCELLENT: All checks passed!\033[0m"
            echo -e "Your system is optimally configured."
        else
            echo -e "\n\033[1;33m✅ GOOD: No critical issues found.\033[0m"
            echo -e "Address warnings for optimal performance."
        fi
    else
        echo -e "\n\033[1;31m❌ ISSUES FOUND: $FAILED_CHECKS critical problem(s) detected.\033[0m"
        echo -e "Please resolve failed checks before proceeding."
        echo -e "Refer to docs/TROUBLESHOOTING.md for help."
    fi

    echo -e "\n\033[1;36mNext Steps:\033[0m"
    if [ "$FAILED_CHECKS" -gt 0 ]; then
        echo -e "  1. Fix critical issues listed above"
        echo -e "  2. Re-run this verification script"
        echo -e "  3. Consult troubleshooting guide if needed"
    else
        echo -e "  1. Your system is ready to use!"
        echo -e "  2. Access the web interface at http://$(hostname).local:3000"
        echo -e "  3. Monitor system health regularly"
    fi

    echo -e "\n\033[1;36mUseful Commands:\033[0m"
    echo -e "  Check services: sudo systemctl status coordinate-camera.service"
    echo -e "  View logs: sudo journalctl -u coordinate-camera.service -f"
    echo -e "  Restart system: sudo systemctl restart coordinate-camera.service"
    echo -e "  Get help: cat docs/TROUBLESHOOTING.md"
}

# Main execution
main() {
    echo -e "\033[1;36m"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║             Coordinate Recorder - System Verification        ║"
    echo "║                                                              ║"
    echo "║  This script checks if your system is properly configured   ║"
    echo "║  and ready to run the Coordinate Recorder application.      ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "\033[0m"

    # Install bc if not available (needed for calculations)
    if ! command -v bc &> /dev/null; then
        echo "Installing bc for calculations..."
        sudo apt-get update && sudo apt-get install -y bc
    fi

    verify_hardware
    verify_camera
    verify_system_dependencies
    verify_permissions
    verify_services
    verify_network
    verify_performance
    generate_summary

    # Return appropriate exit code
    if [ "$FAILED_CHECKS" -gt 0 ]; then
        exit 1
    else
        exit 0
    fi
}

# Run main function
main "$@"
