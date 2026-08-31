#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/capture-display-video.sh [duration_seconds] [output_path]

Examples:
  ./scripts/capture-display-video.sh 120
  ./scripts/capture-display-video.sh 120 /home/pi/coordinate-recorder/videos/demo.mp4
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

duration="${1:-120}"
output_path="${2:-}"

if ! [[ "$duration" =~ ^[0-9]+$ ]]; then
  echo "Duration must be a number (seconds)." >&2
  usage
  exit 1
fi

default_dir="/home/pi/coordinate-recorder/videos"
timestamp="$(date +%Y%m%d_%H%M%S)"
if [[ -z "$output_path" ]]; then
  output_path="${default_dir}/display-${timestamp}.mp4"
fi

mkdir -p "$(dirname "$output_path")"

session_type="${XDG_SESSION_TYPE:-}"
if [[ -n "${WAYLAND_DISPLAY:-}" || "$session_type" == "wayland" ]]; then
  if command -v wf-recorder >/dev/null 2>&1; then
    echo "Wayland session detected. Recording with wf-recorder..."
    output_name="${WLR_OUTPUT:-}"
    if [[ -z "$output_name" ]] && command -v wlr-randr >/dev/null 2>&1; then
      output_name="$(
        wlr-randr | awk '
          /^[^[:space:]]/ { name=$1 }
          /^[[:space:]]*Enabled:[[:space:]]*yes/ { print name; exit }
        '
      )"
    fi
    if [[ -n "$output_name" ]]; then
      timeout -s INT "${duration}s" wf-recorder -o "$output_name" -f "$output_path"
    else
      timeout -s INT "${duration}s" wf-recorder -f "$output_path"
    fi
    echo "Saved: $output_path"
    exit 0
  fi
  echo "Wayland session detected but wf-recorder not found." >&2
fi

display="${DISPLAY:-:0}"
resolution=""
if command -v xrandr >/dev/null 2>&1; then
  resolution="$(xrandr --current | awk '/\*/ {print $1; exit}')"
fi
if [[ -z "$resolution" ]] && command -v xdpyinfo >/dev/null 2>&1; then
  resolution="$(xdpyinfo | awk -F '[ x]+' '/dimensions:/ {print $3 "x" $4; exit}')"
fi
resolution="${resolution:-1280x720}"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found. Install with: sudo apt install -y ffmpeg" >&2
  exit 1
fi

echo "X11 display detected (${display}). Recording ${resolution} for ${duration}s..."
ffmpeg -y \
  -video_size "$resolution" \
  -framerate 30 \
  -f x11grab \
  -i "${display}" \
  -t "${duration}" \
  -movflags +faststart \
  -c:v libx264 \
  -pix_fmt yuv420p \
  "$output_path"

echo "Saved: $output_path"
