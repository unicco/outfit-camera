#!/bin/bash

# Display Brightness Control Script
# Usage: ./display-brightness.sh [dim|bright|off|on|status]

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_ROOT/config/brightness-control.conf"

# Auto-detect backlight device function
# 注意: 戻り値は `BACKLIGHT_DEVICE=$(auto_detect_backlight)` で受ける。診断メッセージは
# すべて stderr(>&2) に出し、stdout にはデバイスパス 1 行だけを書く（混ぜると $() が
# 複数行を取り込み BACKLIGHT_DEVICE が壊れ、点灯が camera_service の直接制御頼みになる）。
auto_detect_backlight() {
    echo "🔍 Auto-detecting backlight device..." >&2
    local backlight_devices=()

    # Search for backlight devices
    for device in /sys/class/backlight/*/bl_power; do
        if [[ -f "$device" ]]; then
            local device_path=$(dirname "$device")
            backlight_devices+=("$device_path")
            echo "   Found: $device_path" >&2
        fi
    done

    if [[ ${#backlight_devices[@]} -eq 0 ]]; then
        echo "❌ No backlight devices found" >&2
        return 1
    elif [[ ${#backlight_devices[@]} -eq 1 ]]; then
        echo "✅ Using auto-detected device: ${backlight_devices[0]}" >&2
        echo "${backlight_devices[0]}"
        return 0
    else
        echo "⚠️ Multiple backlight devices found:" >&2
        for device in "${backlight_devices[@]}"; do
            echo "   - $device" >&2
        done
        echo "✅ Using first device: ${backlight_devices[0]}" >&2
        echo "${backlight_devices[0]}"
        return 0
    fi
}

if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
else
    echo "❌ Configuration file not found: $CONFIG_FILE"
    echo "Using auto-detection..."
    BACKLIGHT_DEVICE=$(auto_detect_backlight)
    if [[ $? -ne 0 ]]; then
        echo "❌ Could not detect backlight device"
        exit 1
    fi
    # Set default values if config file doesn't exist
    BRIGHT_LEVEL=${BRIGHT_LEVEL:-255}
    DIM_LEVEL=${DIM_LEVEL:-10}
    OFF_LEVEL=${OFF_LEVEL:-0}
    POWER_ON=${POWER_ON:-0}
    POWER_OFF=${POWER_OFF:-1}
fi

# Validate/auto-detect backlight device
if [[ ! -d "$BACKLIGHT_DEVICE" ]]; then
    echo "⚠️ Configured device not found: $BACKLIGHT_DEVICE"
    echo "Attempting auto-detection..."
    BACKLIGHT_DEVICE=$(auto_detect_backlight)
    if [[ $? -ne 0 ]]; then
        echo "❌ Could not detect backlight device"
        exit 1
    fi
fi

# File paths based on configuration
BRIGHTNESS_FILE="$BACKLIGHT_DEVICE/brightness"
POWER_FILE="$BACKLIGHT_DEVICE/bl_power"

# sudo は使わない。deploy/udev/99-coordinate-backlight.rules と Raspberry Pi OS 標準の
# 60-backlight.rules が brightness・bl_power を video グループ書き込み可にしている。
# 書けないときは udev rule が当たっていないので、そう言って落とす。
write_backlight() {
    local file=$1 value=$2
    if [ ! -w "$file" ]; then
        echo "❌ Cannot write to $file (device: $BACKLIGHT_DEVICE)"
        echo "   udev rule が当たっていない。bash deploy/setup-pi.sh で配置し直すこと"
        return 1
    fi
    echo "$value" > "$file"
}

set_brightness() {
    local level=$1
    write_backlight "$BRIGHTNESS_FILE" "$level" || return 1
    echo "✅ Brightness set to: $level"
}

set_power() {
    local power=$1
    write_backlight "$POWER_FILE" "$power" || return 1
    echo "✅ Power set to: $([ "$power" -eq 0 ] && echo 'ON' || echo 'OFF')"
}

# Custom brightness level support
if [[ "$1" =~ ^[0-9]+$ ]]; then
    echo "🔆 Setting brightness to: $1"
    set_brightness $1
    exit $?
fi

case "$1" in
    "dim")
        echo "🌑 Dimming display..."
        set_brightness $DIM_LEVEL
        ;;
    "bright")
        echo "🌞 Brightening display..."
        set_brightness $BRIGHT_LEVEL
        ;;
    "medium")
        echo "☀️ Setting medium brightness (100)..."
        set_brightness 100
        ;;
    "off")
        echo "⚫ Turning display OFF..."
        set_brightness $OFF_LEVEL
        set_power $POWER_OFF
        ;;
    "on")
        echo "💡 Turning display ON..."
        set_power $POWER_ON
        set_brightness $BRIGHT_LEVEL
        ;;
    "power-on")
        echo "⚡ Turning display power ON (brightness unchanged)..."
        set_power $POWER_ON
        ;;
    "power-off")
        echo "⚫ Turning display power OFF (brightness unchanged)..."
        set_power $POWER_OFF
        ;;
    "status")
        echo "📊 Display Status (Device: $BACKLIGHT_DEVICE):"
        if [ -f "$BRIGHTNESS_FILE" ]; then
            current_brightness=$(cat "$BRIGHTNESS_FILE" 2>/dev/null || echo "N/A")
            max_brightness=$(cat "$BACKLIGHT_DEVICE/max_brightness" 2>/dev/null || echo "N/A")
            echo "  Brightness: $current_brightness/$max_brightness"
        else
            echo "  Brightness: File not found ($BRIGHTNESS_FILE)"
        fi
        if [ -f "$POWER_FILE" ]; then
            power_state=$(cat "$POWER_FILE" 2>/dev/null || echo "N/A")
            echo "  Power: $([ "$power_state" = "0" ] && echo 'ON' || echo 'OFF')"
        else
            echo "  Power: File not found ($POWER_FILE)"
        fi
        echo "  Configuration levels: DIM=$DIM_LEVEL, BRIGHT=$BRIGHT_LEVEL"
        ;;
    *)
        echo "Usage: $0 [dim|bright|medium|off|on|power-on|power-off|status|<0-255>]"
        echo "  dim       - Set brightness to $DIM_LEVEL"
        echo "  bright    - Set brightness to $BRIGHT_LEVEL"
        echo "  medium    - Set brightness to 100"
        echo "  off       - Turn display completely off (power + brightness)"
        echo "  on        - Turn display on and bright (power + brightness)"
        echo "  power-on  - Turn display power ON only (brightness unchanged)"
        echo "  power-off - Turn display power OFF only (brightness unchanged)"
        echo "  status    - Show current display status"
        echo "  <0-255>   - Set custom brightness level"
        exit 1
        ;;
esac
