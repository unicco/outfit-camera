#!/usr/bin/env python3
"""Helper script to control display power."""
import sys
import os
import glob


def find_backlight_device():
    """Find the first available backlight device."""
    devices = glob.glob("/sys/class/backlight/*/bl_power")
    if devices:
        return os.path.dirname(devices[0])
    return None


def set_power(value):
    """Set display power (0=ON, 1=OFF)."""
    device = find_backlight_device()
    if not device:
        print("Error: No backlight device found", file=sys.stderr)
        return False

    power_file = os.path.join(device, "bl_power")

    try:
        with open(power_file, "w") as f:
            f.write(str(value))
        return True
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False


def set_brightness(value):
    """Set display brightness (0-255)."""
    device = find_backlight_device()
    if not device:
        print("Error: No backlight device found", file=sys.stderr)
        return False

    brightness_file = os.path.join(device, "brightness")

    try:
        with open(brightness_file, "w") as f:
            f.write(str(value))
        return True
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ["on", "off", "dim-off"]:
        print("Usage: display-power-helper.py [on|off|dim-off]")
        sys.exit(1)

    if sys.argv[1] == "on":
        # Turn on with full brightness
        # First set power on, then brightness
        if set_power(0) and set_brightness(255):
            print("Display power set to ON (brightness: 255)")
            sys.exit(0)
    elif sys.argv[1] == "off":
        # Turn off - first dim brightness, then power off
        if set_brightness(0) and set_power(1):
            print("Display power set to OFF")
            sys.exit(0)
    elif sys.argv[1] == "dim-off":
        # Turn off with minimal brightness to keep PIR working
        if set_brightness(10) and set_power(1):
            print("Display power set to OFF (brightness: 10)")
            sys.exit(0)

    sys.exit(1)
