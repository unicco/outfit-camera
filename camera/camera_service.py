#!/usr/bin/env python3
import asyncio
import logging
import math
import os
import platform
import re
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add src to path before other imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import cv2
import numpy as np
import piexif
import requests
import uvicorn
from coordinate_recorder.date_utils import get_effective_date
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image


# Load environment variables from .env file
def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key and value:
                        os.environ[key] = value
        print(f"Loaded environment variables from {env_file}")
    else:
        print(f"No .env file found at {env_file}")


# Load .env file before other imports
load_env_file()


# Determine if we can use Picamera2
try:
    from libcamera import Transform
    from picamera2 import Picamera2

    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# 取り付けの向きを打ち消す 4 分の 1 回転。カメラは箱に 90 度倒して付いている。
# 🚨 **値は Pi 側の設定ファイル（git の外）にあり、コードの既定は回転なし。**
_QUARTER_TURNS = {
    "90": cv2.ROTATE_90_CLOCKWISE,
    "180": cv2.ROTATE_180,
    "270": cv2.ROTATE_90_COUNTERCLOCKWISE,
}

# 微小回転の上限。これを超える傾きは取り付けの異常で、回して隠すものではない
FINE_ROTATION_LIMIT_DEG = 15.0

# 中央切り出しの上限。これを超えると全身が入らない
CENTER_ZOOM_LIMIT = 3.0

_fine_rotation_warned = False
_center_zoom_warned = False


def fine_rotation_deg() -> float:
    """`CAMERA_ROTATION_FINE_DEG` を読む。正の値で反時計回り（右に倒れた絵を起こす）。

    ⚠️ **読めない値・範囲外は 0.0 に倒す。**例外にすると毎朝の記録ごと落ちる。
    ⚠️ 黙ると気づけないので、このプロセスのあいだ 1 回だけ警告を出す
    （毎フレーム失敗する種類の誤設定でログを埋めないため）。
    """
    global _fine_rotation_warned

    raw = os.environ.get("CAMERA_ROTATION_FINE_DEG", "0")
    try:
        degrees = float(raw)
    except ValueError:
        degrees = None

    # 🚨 **`float()` は `nan` と `inf` も通す。**`abs(nan) > 上限` は False なので、
    # 範囲だけ見ていると NaN の行列で warpAffine を呼び、フレームが丸ごと壊れる
    if (
        degrees is None
        or not math.isfinite(degrees)
        or abs(degrees) > FINE_ROTATION_LIMIT_DEG
    ):
        if not _fine_rotation_warned:
            _fine_rotation_warned = True
            logging.getLogger(__name__).warning(
                "CAMERA_ROTATION_FINE_DEG=%s は使えません"
                "（±%s 度に収まる数値であること）。傾き補正なしで続けます",
                raw,
                FINE_ROTATION_LIMIT_DEG,
            )
        return 0.0
    return degrees


def cover_scale(size: tuple[int, int], degrees: float) -> float:
    """回しても黒い角が出ない最小の拡大率。`size` は (幅, 高さ)。

    出力の四隅を逆回転しても元画像の内側に残る、という条件から出る
    （cos|θ| + max(縦横比, 横縦比) × sin|θ|）。

    ⚠️ **拡大したぶんだけ写る範囲が狭くなる。**しかも**細長い画ほど高くつく**
    （1080×1920 を 2 度回すと 6% 拡大＝上下左右がそのぶん欠ける）。
    """
    width, height = size
    radians = math.radians(abs(degrees))
    ratio = max(width / height, height / width)
    return math.cos(radians) + ratio * math.sin(radians)


def center_zoom() -> float:
    """`CAMERA_CENTER_ZOOM` を読む。`1.0` で切り出しなし。

    中央だけを使うと**広角レンズの歪みが小さい中心部に寄る**ので、顔の引き伸ばしが減る
。⚠️ 拡大したぶん写る範囲は狭くなる。

    ⚠️ **1.0 未満は受け付けない。**縮小すると出力の外側が埋められない（縁の色が伸びた帯になる）。
    ⚠️ 読めない値・範囲外は 1.0 に倒す。撮影を止めるほうが困る。
    """
    global _center_zoom_warned

    raw = os.environ.get("CAMERA_CENTER_ZOOM", "1")
    try:
        value = float(raw)
    except ValueError:
        value = None

    if (
        value is None
        or not math.isfinite(value)
        or not 1.0 <= value <= CENTER_ZOOM_LIMIT
    ):
        if not _center_zoom_warned:
            _center_zoom_warned = True
            logging.getLogger(__name__).warning(
                "CAMERA_CENTER_ZOOM=%s は使えません"
                "（1.0 以上 %s 以下の数値であること）。切り出しなしで続けます",
                raw,
                CENTER_ZOOM_LIMIT,
            )
        return 1.0
    return value


def effective_zoom(size: tuple[int, int], degrees: float, requested: float) -> float:
    """実際に掛ける拡大率。`requested` は `CAMERA_CENTER_ZOOM`。

    ⭐ **中央切り出しがあれば、回転のぶんの拡大は無料になる。**切り出す領域が元画像の
    内側に収まっていれば黒い角は出ないので、`cover_scale` を上乗せする必要がない。
    実機の `+4.1 度` は単体だと 12.5% 食うが、切り出し 1.5 倍と併用すればゼロコスト。
    """
    return max(requested, cover_scale(size, degrees))


def shared_sensor_mode(
    modes: list[dict], sizes: list[tuple[int, int]]
) -> tuple[int, int] | None:
    """どの出力解像度も同じ画角で賄えるセンサーモードを 1 つ選ぶ。

    🚨 **モードが変わると読む範囲が変わる**ので、待機用と撮影用で別のモードに落ちると
    ライブ映像と撮った写真で構図が食い違う。実測値は
    `docs/setup/touchscreen-setup.md`「解像度設定」。

    ⚠️ 賄えるモードが無ければ `None`。呼ぶ側は指定なし（従来どおりの自動選択）に倒す。
    """
    if not modes or not sizes:
        return None
    need_width = max(width for width, _ in sizes)
    need_height = max(height for _, height in sizes)
    covering = [
        mode["size"]
        for mode in modes
        if mode["size"][0] >= need_width and mode["size"][1] >= need_height
    ]
    if not covering:
        return None
    return min(covering, key=lambda size: size[0] * size[1])


def orient_frame(frame: np.ndarray) -> np.ndarray:
    """カメラのフレームを、見せる・保存する向きに直す。

    🚨 **フレームを外へ出す経路は必ずここを通す**（`/stream`・`/capture/preview`・
    `/capture`）。経路ごとに書くと、ライブ映像と撮った写真で構図が食い違う
。
    """
    quarter_turn = _QUARTER_TURNS.get(os.environ.get("CAMERA_STREAM_ROTATION", "0"))
    if quarter_turn is not None:
        frame = cv2.rotate(frame, quarter_turn)

    degrees = fine_rotation_deg()
    height, width = frame.shape[:2]
    # ⭐ **回転と中央切り出しは 1 つの変換にまとめる。**別々に掛けると 2 回サンプリングして
    # 眠くなるうえ、回転のための拡大が切り出しに上乗せされて余計に画角を失う
    zoom = effective_zoom((width, height), degrees, center_zoom())
    if degrees == 0.0 and zoom == 1.0:
        return frame

    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), degrees, zoom)
    # 端の丸めで黒が 1px 出ることがあるので、外側は縁の色で埋める
    return cv2.warpAffine(
        frame,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )


class CameraService:
    def __init__(self, *, pir_simulation_mode: bool = False):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Starting camera initialization...")

        # Validate environment variables before proceeding
        self._validate_environment_variables()

        self.pir_simulation_mode = pir_simulation_mode

        # Upload functionality moved to UI (no longer automatic)

        # Get camera mode from environment, defaulting to hardware for Raspberry Pi
        self.camera_mode = os.environ.get("CAMERA_MODE", "hardware")
        self.logger.info(f"Camera mode from env: {self.camera_mode}")
        self.logger.info(
            f"CAMERA_MODE env var: {os.environ.get('CAMERA_MODE', 'NOT SET')}"
        )
        self.logger.info(
            f"All env vars: {[k for k in os.environ.keys() if 'CAMERA' in k or 'MODE' in k]}"
        )

        # Use BACKEND_API_URL if available, fall back to API_URL for backward compatibility
        self.api_url = os.environ.get(
            "BACKEND_API_URL", os.environ.get("API_URL", "http://localhost:8000")
        )
        self.photos_dir = os.path.expanduser(os.environ.get("PHOTOS_DIR", "./photos"))
        os.makedirs(self.photos_dir, exist_ok=True)

        # 未送信マークの置き場。撮影は成功しても API に届かないことがあり（Wi-Fi 断など）、
        # 届くまでここに印を残して再送する。photos_dir の外に置くのは、写真を走査する
        # 処理（orphan 掃除など）に紛れさせないため
        self.unsent_dir = os.path.expanduser(
            os.environ.get(
                "UNSENT_MARKER_DIR", "~/.local/state/coordinate-recorder/unsent"
            )
        )
        os.makedirs(self.unsent_dir, exist_ok=True)
        # 再送の間隔と、未送信のまま放置されていると判断するまでの時間
        self.unsent_retry_interval = int(
            os.environ.get("UNSENT_RETRY_INTERVAL_SECONDS", "300")
        )
        self.unsent_stale_seconds = int(os.environ.get("UNSENT_STALE_SECONDS", "86400"))
        self.stop_unsent_retry = False
        # 再送は定期ループと halt 直前の 2 経路から呼ばれる。存在確認と送信の間に
        # 割り込まれると、両方が「まだ届いていない」と判断して二重送信になる。
        # API が冪等になった今も、同じ写真を 2 回上げる無駄は避ける
        self.unsent_lock = threading.Lock()

        # 🔥 発熱対策: 解像度設定を全モードで初期化
        self.detection_width = int(os.environ.get("CAMERA_DETECTION_WIDTH", "640"))
        self.detection_height = int(os.environ.get("CAMERA_DETECTION_HEIGHT", "480"))
        self.detection_resolution = (self.detection_width, self.detection_height)

        capture_width = int(os.environ.get("CAMERA_CAPTURE_WIDTH", "1920"))
        capture_height = int(os.environ.get("CAMERA_CAPTURE_HEIGHT", "1080"))
        self.capture_resolution = (capture_width, capture_height)

        # 待機用と撮影用が共有するセンサーモード。実機の初期化時に決まる
        # （`shared_sensor_mode`）。決められなければ None＝従来どおりの自動選択
        self.sensor_mode: tuple[int, int] | None = None

        self.picamera2 = None

        # Display control configuration (simplified)
        self.display_timeout = int(os.environ.get("PIR_INACTIVITY_TIMEOUT", "30"))
        self.display_off_timer = None
        self.display_state = "off"  # off/on の2状態のみ
        self.display_state_lock = threading.Lock()
        self.last_display_time = 0

        # Periodic resource cleanup configuration
        self.resource_cleanup_interval = int(
            os.environ.get("RESOURCE_CLEANUP_INTERVAL", "3600")
        )  # 1 hour
        self.max_pir_history_age = int(
            os.environ.get("MAX_PIR_HISTORY_AGE", "300")
        )  # 5 minutes
        self.resource_cleanup_timer = None
        self.last_resource_cleanup = time.time()
        self._last_manual_restart_time = 0.0

        # 🔒 Camera resource lock for motion detection and capture exclusion
        self.camera_lock = threading.Lock()
        self.camera_sync_lock = threading.Lock()  # For streaming synchronization
        self.is_capturing = False

        # 🔒 PIR sensor lock for thread-safe access
        self.pir_sensor_lock = threading.Lock()

        # 🔥 熱対策: 温度監視・制御機能
        self.cpu_temperature = 0.0
        self.thermal_throttle_level = 0  # 0: 正常, 1: 軽度制御, 2: 重度制御
        self.thermal_monitor_thread = None
        self.stop_thermal_monitor = False

        # 🔥 熱対策: 温度閾値定数
        self.THERMAL_LIGHT_THROTTLE = 75.0  # 軽度制御開始温度 (°C)
        self.THERMAL_HEAVY_THROTTLE = 80.0  # 重度制御開始温度 (°C)
        self.THERMAL_RECOVERY = 60.0  # 制御解除温度 (°C)
        self.THERMAL_MONITOR_INTERVAL = float(
            os.environ.get("THERMAL_MONITOR_INTERVAL", "30")
        )  # 監視間隔 (秒)

        # Camera mode
        self.current_mode = "sleep"  # sleep/active states

        # Log display configuration
        self.logger.info(f"Display timeout: {self.display_timeout}s (fixed)")

        # PIR sensor configuration
        self.pir_enabled = os.environ.get("PIR_ENABLED", "false").lower() == "true"
        self.pir_gpio_pin = int(os.environ.get("PIR_GPIO_PIN", "18"))
        self.pir_detection_threshold = int(
            os.environ.get("PIR_DETECTION_THRESHOLD", "2")
        )
        self.pir_detection_window = int(os.environ.get("PIR_DETECTION_WINDOW", "3"))
        self.camera_active_duration = int(
            os.environ.get("CAMERA_ACTIVE_DURATION", "300")
        )  # 5 minutes
        self.pir_simulation_mode = (
            os.environ.get("PIR_SIMULATION_MODE", "false").lower() == "true"
        )

        # 自動シャットダウン設定（イベント駆動電源運用）。安全のためデフォルト無効で、
        # 本番運用時のみ AUTO_SHUTDOWN_ENABLED=true にする（false の間は /shutdown も
        # スケジュール halt も一切落とさない）。halt の発火源は次の 4 つ:
        #   ① 撮影＋アップロード完了で UI が POST /shutdown（記録が済んだら即落とす）
        #   ② 毎日 DAILY_SHUTDOWN_TIME（既定 20:00 JST）を過ぎたら halt（撮影の有無は見ない）
        #   ③ NTP が一度も同期しないまま MAX_UNSYNCED_UPTIME_SECONDS 経過（② が効かない日の砦）
        #   ④ 最終バックストップ: MAX_UPTIME_SECONDS 経過
        self.auto_shutdown_enabled = (
            os.environ.get("AUTO_SHUTDOWN_ENABLED", "false").lower() == "true"
        )
        # ② の cutoff 時刻（JST・"HH:MM"）。この時刻を過ぎて残っている Pi を落とす。
        self.daily_shutdown_hour, self.daily_shutdown_minute = self._parse_hhmm(
            os.environ.get("DAILY_SHUTDOWN_TIME", "20:00"), default=(20, 0)
        )
        # ④ 壁時計に依らず、システム起動からこの秒数を超えたら必ず halt。Pi が無期限に
        # 点いたまま（イベント駆動電源運用が破綻）になるのを防ぐ。
        self.max_uptime_seconds = int(
            os.environ.get("MAX_UPTIME_SECONDS", "57600")  # 16 時間
        )
        # ③ ② は NTP 同期後しか判定しないため、同期しない日は ④ の 16 時間まで点きっぱなしに
        # なる窓が空く（で 10 時間）。既定 6 時間は HA のプラグ ON が 07:00-10:00・
        # 1 日 1 回である前提で、正常な撮影機会を残せる値として選んだ。同期済の日はこの条件を
        # 通らないので通常運用には影響しない。
        self.max_unsynced_uptime_seconds = int(
            os.environ.get("MAX_UNSYNCED_UPTIME_SECONDS", "21600")  # 6 時間
        )
        # ⚠️ 経過時間は壁時計（time.time()）で測らない。この Pi は RTC バッテリーが無く、
        # 起動時クロックは fake-hwclock が前回 halt 時刻（≒前夜 20:00）に復元 → NTP 同期で
        # 大ジャンプする。壁時計を使う ② は NTP 同期確認（_is_clock_synced）でガードし、未同期の
        # うちは判定しない（朝の起動直後に復元値 20:00 で誤 halt するのを防ぐ）。
        # フォールバック用（/proc が無い環境）。実測は _uptime_seconds() を使う。
        self.service_start_monotonic = time.monotonic()
        self._clock_ever_synced = False
        # systemd-timesyncd が同期時に作るフラグ。/run は tmpfs なので boot ごとに消える。
        self.clock_synced_flag_path = "/run/systemd/timesync/synchronized"
        self.stop_shutdown_monitor = False
        self._shutdown_in_progress = False

        # PIR sensor state management
        self.pir_sensor = None
        self.pir_detections = []
        self.daily_photo_taken = False
        self.last_photo_date = None
        self._pir_monitoring_stop_event = None

        # API capture status cache (reduce API calls)
        self._capture_status_cache = None
        self._capture_status_cache_time = 0
        self._capture_status_cache_duration = 180  # 3 minutes cache

        # Manual photo capture triggers automatic AI detection

        self.logger.info(f"PIR sensor enabled: {self.pir_enabled}")
        self.logger.info(f"PIR GPIO pin: {self.pir_gpio_pin}")
        self.logger.info(
            f"PIR detection threshold: {self.pir_detection_threshold} detections "
            f"in {self.pir_detection_window}s"
        )
        self.logger.info(
            f"Camera active duration: {self.camera_active_duration}s (5 minutes)"
        )
        self.logger.info(f"PIR simulation mode: {self.pir_simulation_mode}")

        # Backlight device auto-detection
        self.backlight_device = self._detect_backlight_device()

        # Service start time for uptime tracking
        self.start_time = time.time()

        self._init_camera()

        # Initialize PIR sensor if enabled
        if self.pir_enabled:
            self._init_pir_sensor()

        # Automatic upload disabled - handled by UI

        # 🔥 熱対策: 温度監視バックグラウンドタスク開始
        self.logger.info(
            f"🔥 Thermal control configuration: Light={self.THERMAL_LIGHT_THROTTLE}°C, "
            f"Heavy={self.THERMAL_HEAVY_THROTTLE}°C, Recovery={self.THERMAL_RECOVERY}°C"
        )
        self.logger.info(
            f"🔥 Thermal monitor interval: {self.THERMAL_MONITOR_INTERVAL}s"
        )
        self._start_thermal_monitor()

        # 🧹 定期的リソースクリーンアップ開始
        self._start_periodic_resource_cleanup()

        # ⏻ スケジュール自動シャットダウン監視開始（AUTO_SHUTDOWN_ENABLED 時のみ実働）
        self._start_shutdown_monitor()
        self._start_unsent_retry_monitor()

    def _sensor_kwargs(self) -> dict:
        """`create_still_configuration` に渡すセンサーモードの指定。

        ⚠️ **3 つの configuration すべてに同じものを渡す**（待機・撮影・撮影後の戻し）。
        1 つでも外すとそこだけ別のモードに落ちて画角が変わる。
        """
        if self.sensor_mode is None:
            return {}
        return {"raw": {"size": self.sensor_mode}}

    def _init_camera(self):
        self.logger.info(f"_init_camera called with mode: {self.camera_mode}")

        if self.camera_mode == "hardware":
            self.logger.info("Hardware mode: Attempting Picamera2 initialization...")
            self.logger.info(f"PICAMERA2_AVAILABLE: {PICAMERA2_AVAILABLE}")

            if PICAMERA2_AVAILABLE:
                try:
                    self.logger.info("Creating Picamera2 instance...")
                    self.picamera2 = Picamera2()

                    self.logger.info("Getting camera properties...")
                    camera_info = self.picamera2.camera_properties
                    self.logger.info(f"Found camera: {camera_info}")

                    # Get maximum resolution from camera sensor
                    self.logger.info("Creating camera configuration...")

                    # Get sensor modes to find maximum resolution
                    sensor_modes = self.picamera2.sensor_modes
                    if sensor_modes:
                        # Find the mode with highest resolution
                        max_mode = max(
                            sensor_modes,
                            key=lambda mode: mode["size"][0] * mode["size"][1],
                        )
                        max_resolution = max_mode["size"]
                        self.logger.info(
                            f"Maximum sensor resolution: {max_resolution[0]}x{max_resolution[1]}"
                        )
                    else:
                        # Default to 4K if sensor modes not available
                        max_resolution = (3840, 2160)
                        self.logger.info(
                            "Sensor modes not available, using 4K resolution"
                        )

                    # 🔥 発熱対策: 人検知用とキャプチャ用で解像度を分離
                    # 人検知用低解像度 (CPU負荷大幅削減)
                    self.detection_width = int(
                        os.environ.get("CAMERA_DETECTION_WIDTH", "640")
                    )
                    self.detection_height = int(
                        os.environ.get("CAMERA_DETECTION_HEIGHT", "480")
                    )
                    self.detection_resolution = (
                        self.detection_width,
                        self.detection_height,
                    )

                    # 撮影時の高解像度 (撮影時のみ使用)
                    capture_width = int(os.environ.get("CAMERA_CAPTURE_WIDTH", "1920"))
                    capture_height = int(
                        os.environ.get("CAMERA_CAPTURE_HEIGHT", "1080")
                    )
                    self.capture_resolution = (capture_width, capture_height)

                    # 初期設定は人検知用低解像度 (発熱抑制)
                    resolution = self.detection_resolution

                    # 🚨 **待機用と撮影用で同じセンサーモードに固定する。**要求解像度に
                    # 任せると別のモードに落ちて画角が変わる（`shared_sensor_mode`）
                    self.sensor_mode = shared_sensor_mode(
                        sensor_modes,
                        [self.detection_resolution, self.capture_resolution],
                    )
                    if self.sensor_mode is None:
                        # ⚠️ 固定できない＝画角が食い違う条件に戻る。撮影は止めないが、
                        # INFO で流すと気づけないので警告で残す
                        self.logger.warning(
                            "センサーモードを固定できませんでした"
                            f"（待機 {self.detection_resolution}・"
                            f"撮影 {self.capture_resolution} を賄うモードが無い）。"
                            "ライブ映像と撮った写真で画角が変わりえます"
                        )
                    else:
                        self.logger.info(f"Shared sensor mode: {self.sensor_mode}")

                    self.logger.info("🔥 Heat optimization enabled:")
                    self.logger.info(
                        f"  Detection resolution: {self.detection_resolution[0]}x{self.detection_resolution[1]} "
                        f"(for motion detection)"
                    )
                    self.logger.info(
                        f"  Capture resolution: {self.capture_resolution[0]}x{self.capture_resolution[1]} "
                        f"(for photo capture)"
                    )
                    self.logger.info(
                        f"Using initial resolution: {resolution[0]}x{resolution[1]}"
                    )

                    # Get white balance settings from environment
                    awb_mode = os.environ.get("CAMERA_AWB_MODE", "indoor")

                    # Map AWB mode names to libcamera values
                    awb_modes = {
                        "auto": 0,
                        "indoor": 1,  # Incandescent/Tungsten (2500K-3000K)
                        "fluorescent": 3,  # Fluorescent (4000K-5000K)
                        "daylight": 5,  # Daylight (5000K-6500K)
                        "cloudy": 6,  # Cloudy (6500K-7500K)
                        "custom": 7,
                    }

                    awb_value = awb_modes.get(awb_mode, 1)  # Default to indoor

                    # Auto exposure mode
                    controls = {
                        "AwbMode": awb_value,
                        "AeEnable": True,  # Enable auto exposure
                    }

                    self.logger.info("Using auto exposure mode")

                    # Add custom white balance gains if specified
                    if awb_mode == "custom":
                        # Get custom color gains from environment
                        red_gain = float(os.environ.get("CAMERA_AWB_RED_GAIN", "1.9"))
                        blue_gain = float(os.environ.get("CAMERA_AWB_BLUE_GAIN", "1.5"))
                        controls["ColourGains"] = (red_gain, blue_gain)
                        self.logger.info(
                            f"Using custom white balance: red={red_gain}, blue={blue_gain}"
                        )

                    self.logger.info(
                        f"Using white balance mode: {awb_mode} (value={awb_value})"
                    )

                    # Camera orientation transform (configurable via environment variables)
                    vflip = os.environ.get("CAMERA_VFLIP", "true").lower() == "true"
                    hflip = os.environ.get("CAMERA_HFLIP", "true").lower() == "true"
                    portrait_transform = Transform(vflip=vflip, hflip=hflip)

                    config = self.picamera2.create_still_configuration(
                        main={"size": resolution},  # Use maximum resolution
                        buffer_count=1,
                        queue=False,
                        controls=controls,
                        transform=portrait_transform,  # Portrait orientation for full-body photos
                        **self._sensor_kwargs(),
                    )

                    self.logger.info("Configuring camera...")
                    self.picamera2.configure(config)

                    self.logger.info("Starting camera...")
                    self.picamera2.start()

                    # Apply initial camera settings
                    self.logger.info("Applying initial camera settings...")
                    self.picamera2.set_controls(controls)

                    self.logger.info("Picamera2 initialization completed successfully")
                except Exception as e:
                    self.logger.error(
                        f"Failed to initialize Picamera2: {type(e).__name__}: {e}"
                    )
                    import traceback

                    self.logger.error(f"Traceback: {traceback.format_exc()}")

                    # Additional diagnostic information
                    self.logger.error(f"Current working directory: {os.getcwd()}")
                    self.logger.error(f"Process user: {os.getenv('USER', 'unknown')}")

                    # Check camera device files
                    try:
                        import glob

                        video_devices = glob.glob("/dev/video*")
                        self.logger.error(f"Available video devices: {video_devices}")
                    except Exception:
                        self.logger.error("Could not check video devices")

                    raise RuntimeError(f"Picamera2 initialization failed: {e}") from e
            else:
                raise RuntimeError("Picamera2 module not available")
        elif self.camera_mode == "simulation":
            self.logger.info(
                "Camera initialized in simulation mode (no physical camera required)"
            )
            self.picamera2 = None  # No actual camera in simulation mode
        else:
            raise RuntimeError(f"Unsupported camera mode: {self.camera_mode}")

    def restart_camera_subsystem(self):
        """Restart Picamera2 without restarting the whole service."""
        with self.camera_lock:
            self.logger.info("🔄 Manual camera restart requested via API/touchscreen")

            if self.camera_mode != "hardware":
                message = (
                    "Camera restart skipped because service is not in hardware mode"
                )
                self.logger.info(message)
                return {
                    "status": "skipped",
                    "camera_mode": self.camera_mode,
                    "message": message,
                }

            if not PICAMERA2_AVAILABLE:
                message = "Picamera2 module not available; cannot restart camera"
                self.logger.warning(message)
                return {
                    "status": "skipped",
                    "camera_mode": self.camera_mode,
                    "message": message,
                }

            try:
                now = time.time()
                cooldown = float(
                    os.environ.get("CAMERA_RESTART_COOLDOWN_SECONDS", "30")
                )
                if now - self._last_manual_restart_time < cooldown:
                    wait_time = int(cooldown - (now - self._last_manual_restart_time))
                    message = f"Camera restart skipped due to cooldown ({wait_time}s remaining)"
                    self.logger.warning(message)
                    return {
                        "status": "cooldown",
                        "camera_mode": self.camera_mode,
                        "message": message,
                    }

                if self.picamera2:
                    try:
                        self.picamera2.stop()
                        self.logger.info("Picamera2 stopped for restart")
                    except Exception as stop_error:
                        self.logger.warning(
                            f"Failed to stop Picamera2 cleanly: {stop_error}"
                        )
                    try:
                        self.picamera2.close()
                        self.logger.info("Picamera2 closed for restart")
                    except Exception as close_error:
                        self.logger.warning(
                            f"Failed to close Picamera2 cleanly: {close_error}"
                        )
                    self.picamera2 = None

                    # Allow hardware to settle before re-initialization
                    time.sleep(
                        0.5
                    )  # Give ISP pipeline time to release hardware handles

                self._init_camera()
                self._last_manual_restart_time = now
                message = "Camera subsystem restarted successfully"
                self.logger.info(message)
                return {
                    "status": "success",
                    "camera_mode": self.camera_mode,
                    "message": message,
                }
            except Exception as e:
                self.logger.error(f"Manual camera restart failed: {e}")
                raise RuntimeError(f"Manual camera restart failed: {e}") from e

    def capture_photo(self, force_capture=False, trigger_source="unknown"):
        """撮影を実行.

        Args:
            force_capture: 強制撮影フラグ
            trigger_source: 撮影トリガー源（"touchscreen", "api", "pir", "auto", "manual"）

        """
        # 🔒 排他制御: 人検知ループとキャプチャが同時にカメラにアクセスしないよう制御
        with self.camera_lock:
            if self.is_capturing:
                self.logger.warning("Capture already in progress, skipping...")
                return None

            self.is_capturing = True

            # 📸 詳細な撮影トリガーログを記録
            import inspect

            caller_info = inspect.stack()[1] if len(inspect.stack()) > 1 else None
            caller_context = (
                f"{caller_info.filename}:{caller_info.lineno}"
                if caller_info
                else "unknown"
            )

            self.logger.info(
                f"📸 PHOTO CAPTURE INITIATED - "
                f"Trigger: {trigger_source} | "
                f"Force: {force_capture} | "
                f"Caller: {caller_context} | "
                f"Timestamp: {datetime.now().isoformat()}"
            )

            try:
                return self._do_capture_photo(force_capture, trigger_source)
            finally:
                self.is_capturing = False
                self.logger.info("🔓 Camera unlocked after capture")

    def _do_capture_photo(self, force_capture=False, trigger_source="unknown"):
        try:
            self.logger.info(f"Starting photo capture... (trigger: {trigger_source})")
            timestamp = datetime.now()
            filename = f"photo_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = os.path.join(self.photos_dir, filename)

            # Initialize frame_bgr to None to ensure proper error handling
            frame_bgr = None

            if self.picamera2:
                self.logger.info("🔥 Capturing with Picamera2 at high resolution...")

                # 撮影時のみ高解像度に一時切り替え (発熱対策)
                capture_failed = False

                try:
                    # ⚠️ 重要: Picamera2の解像度変更には stop() → configure() → start() が必要
                    self.logger.info("Stopping camera for resolution switch...")
                    self.picamera2.stop()

                    # 高解像度設定で一時的に再構成（環境変数の向き設定を維持）
                    vflip = os.environ.get("CAMERA_VFLIP", "true").lower() == "true"
                    hflip = os.environ.get("CAMERA_HFLIP", "true").lower() == "true"
                    portrait_transform = Transform(vflip=vflip, hflip=hflip)
                    capture_config = self.picamera2.create_still_configuration(
                        main={"size": self.capture_resolution},
                        buffer_count=1,
                        queue=False,
                        transform=portrait_transform,  # Portrait orientation for full-body photos
                        **self._sensor_kwargs(),
                    )
                    self.logger.info(
                        f"Switching to capture resolution: "
                        f"{self.capture_resolution[0]}x{self.capture_resolution[1]}"
                    )
                    self.picamera2.configure(capture_config)
                    self.picamera2.start()

                    # Wait for auto exposure to stabilize
                    time.sleep(0.5)

                    # Log current exposure settings
                    metadata = self.picamera2.capture_metadata()
                    self.logger.info(
                        f"Exposure metadata - Time: {metadata.get('ExposureTime', 'N/A')}μs, "
                        f"Gain: {metadata.get('AnalogueGain', 'N/A')}, "
                        f"Digital Gain: {metadata.get('DigitalGain', 'N/A')}, "
                        f"Lux: {metadata.get('Lux', 'N/A')}"
                    )

                    # 高解像度で撮影（Transform で既に縦向き設定済）
                    raw_array = self.picamera2.capture_array("main")
                    if raw_array is not None:
                        frame_bgr = cv2.cvtColor(raw_array, cv2.COLOR_RGB2BGR)

                        frame_bgr = orient_frame(frame_bgr)
                    else:
                        self.logger.error("Failed to capture array from Picamera2")
                        capture_failed = True

                except Exception as e:
                    self.logger.error(f"Error during high-resolution capture: {e}")
                    import traceback

                    self.logger.error(f"Traceback: {traceback.format_exc()}")
                    capture_failed = True
                    frame_bgr = None

                finally:
                    try:
                        # 即座に低解像度に戻す (発熱抑制)
                        self.logger.info(
                            "Stopping camera for resolution switch back..."
                        )
                        self.picamera2.stop()

                        vflip = os.environ.get("CAMERA_VFLIP", "true").lower() == "true"
                        hflip = os.environ.get("CAMERA_HFLIP", "true").lower() == "true"
                        portrait_transform = Transform(vflip=vflip, hflip=hflip)
                        detection_config = self.picamera2.create_still_configuration(
                            main={"size": self.detection_resolution},
                            buffer_count=1,
                            queue=False,
                            transform=portrait_transform,  # Portrait orientation for consistent streaming
                            **self._sensor_kwargs(),
                        )
                        self.logger.info(
                            f"Switching back to detection resolution: {self.detection_resolution[0]}x{self.detection_resolution[1]}"
                        )
                        self.picamera2.configure(detection_config)
                        self.picamera2.start()
                        self.logger.info(
                            "🔥 Resolved to low resolution for heat control"
                        )
                    except Exception as e:
                        self.logger.error(
                            f"Error switching back to detection resolution: {e}"
                        )
                        capture_failed = True

                if capture_failed or frame_bgr is None:
                    self.logger.error(
                        "Capture failed due to resolution switching error or capture failure"
                    )
                    return None
            elif self.camera_mode == "simulation":
                self.logger.info("📷 Creating simulation photo...")
                # Create a simple simulation image with timestamp
                height, width = 480, 640
                frame_bgr = np.random.randint(
                    0, 255, (height, width, 3), dtype=np.uint8
                )

                # Add timestamp text to the image
                text = f"SIMULATION {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                cv2.putText(
                    frame_bgr,
                    text,
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (255, 255, 255),
                    2,
                )
                cv2.putText(
                    frame_bgr,
                    "Camera Simulation Mode",
                    (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )
                self.logger.info("✅ Simulation photo generated")
            else:
                self.logger.error("No valid camera available for capture")
                return None

            # Validate frame_bgr before attempting to save
            if frame_bgr is None:
                self.logger.error("frame_bgr is None, cannot save photo")
                return None

            # Save the image
            success = cv2.imwrite(filepath, frame_bgr)
            if not success:
                self.logger.error(f"Failed to save photo to {filepath}")
                return None

            # Add EXIF data with JST timezone information
            try:
                self._add_exif_data(filepath, timestamp)
            except Exception as e:
                self.logger.warning(f"Failed to add EXIF data: {e}")

            self.logger.info(f"Photo saved: {filename}")

            # アップロードは UI が担う。ここでは送るべき写真として印だけ残し、
            # UI が失敗したまま忘れても再送ループが拾えるようにする
            self._mark_unsent(filename)
            self.logger.info(f"Photo saved locally: {filename}")

            # PIRセンサー統合: 撮影成功時の処理
            if self.pir_enabled:
                self._mark_daily_photo_taken()

            return filename

        except Exception as e:
            self.logger.error(f"Error during photo capture: {e}")
            return None

    def _add_exif_data(self, filepath, timestamp):
        """Add EXIF data with JST timezone information to the photo."""
        try:
            # Format timestamp in JST (EXIF format: "YYYY:MM:DD HH:MM:SS")
            exif_datetime = timestamp.strftime("%Y:%m:%d %H:%M:%S")

            # Create EXIF data with piexif
            exif_dict = {
                "0th": {},
                "Exif": {
                    piexif.ExifIFD.DateTimeOriginal: exif_datetime.encode(),
                    piexif.ExifIFD.DateTimeDigitized: exif_datetime.encode(),
                },
                "1st": {},
                "thumbnail": None,
                "GPS": {},
            }

            # Add DateTime to 0th IFD as well
            exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_datetime.encode()

            # Convert to bytes
            exif_bytes = piexif.dump(exif_dict)

            # Save image with EXIF data
            img = Image.open(filepath)
            img.save(filepath, "JPEG", quality=95, exif=exif_bytes)

            self.logger.debug(
                f"Added EXIF data to {filepath} with JST timestamp: {exif_datetime}"
            )

        except Exception as e:
            self.logger.error(f"Error adding EXIF data: {e}")
            raise

    def send_to_backend(self, filepath, captured_date=None):
        """Send photo to backend.

        captured_date（"YYYY-MM-DD"）を渡さないと API は受信時刻で記録する。撮影当日に
        送るぶんには同じだが、後日の再送では「送った日」になってしまうので、
        再送する側は必ず渡すこと。

        AI 衣類検出はここから叩かない。API が upload の中でバックグラウンド実行する
        （api/app/routers/upload.py）ので、Pi から重ねて叩くと二重呼び出しになる。

        source は "camera_retry" 固定。この関数を通るのは再送だけで、撮影直後の
        通常アップロードは UI が直接 API を叩く。
        """
        try:
            if not os.path.exists(filepath):
                self.logger.error(f"File not found for upload: {filepath}")
                return False

            self.logger.info(f"Sending photo to backend: {filepath}")

            with open(filepath, "rb") as f:
                files = {"file": (os.path.basename(filepath), f, "image/jpeg")}
                # 経路を API に名乗る。ここを通るのは再送だけで、
                # 撮影直後の通常アップロードは UI が直接送る
                data = {"source": "camera_retry"}
                if captured_date:
                    data["captured_date"] = captured_date
                # Use correct API endpoint
                endpoint = f"{self.api_url}/v2/upload"

                try:
                    response = requests.post(
                        endpoint, files=files, data=data, timeout=30
                    )
                    if response.status_code == 200:
                        self.logger.info(
                            f"Photo sent to backend successfully via {endpoint}"
                        )
                        return True
                    else:
                        self.logger.warning(
                            f"Failed at {endpoint}: {response.status_code}"
                        )
                        return False
                except requests.exceptions.Timeout:
                    self.logger.warning(f"Request timeout at {endpoint}")
                    return False
                except requests.exceptions.ConnectionError as e:
                    self.logger.warning(f"Connection error at {endpoint}: {e}")
                    return False
                except requests.exceptions.RequestException as e:
                    self.logger.warning(f"Request failed at {endpoint}: {e}")
                    return False

        except Exception as e:
            self.logger.error(f"Error sending photo to backend: {e}")
            return False

    def _mark_unsent(self, filename):
        """写真を「まだ API に届いていない」として印を付ける（中身は持たない空ファイル）."""
        try:
            with open(os.path.join(self.unsent_dir, filename), "w"):
                pass
        except Exception as e:
            self.logger.error(f"Failed to mark {filename} as unsent: {e}")

    def _clear_unsent(self, filename):
        try:
            os.remove(os.path.join(self.unsent_dir, filename))
        except FileNotFoundError:
            pass
        except Exception as e:
            self.logger.error(f"Failed to clear unsent mark for {filename}: {e}")

    def _is_marked_unsent(self, filename):
        return os.path.exists(os.path.join(self.unsent_dir, filename))

    def discard_unsent(self, filename):
        """撮り直しで捨てた写真を再送の対象から外す.

        写真そのものは消さない。記録に載せないという目的は印の削除で足りるし、残して
        おけば誤タップを POST /upload/{photo_id} で救える。
        unsent_lock は取らない。印の削除は単発の os.remove で壊れようがなく、送信中の
        1 件は _upload_if_missing_locked 側の再確認で止まるため（ロックを待つと、疎通が
        悪いときに UI が数十秒固まる）。
        返り値は印が実際にあったか。UI は撮り直しのたびに投げるので、無いこと自体は異常でない。
        """
        was_marked = self._is_marked_unsent(filename)
        self._clear_unsent(filename)
        if was_marked:
            self.logger.info(f"Discarded retaken photo: {filename}")
        return was_marked

    def list_unsent(self):
        """未送信マークのファイル名を古い順に返す."""
        try:
            names = [n for n in os.listdir(self.unsent_dir) if n.endswith(".jpg")]
        except FileNotFoundError:
            return []
        return sorted(names)

    def _photo_exists_on_backend(self, photo_id):
        """API に既にこの写真があるかを返す（不明なときは None）.

        API は photo_id で冪等になったので、確認を飛ばしても重複レコードは
        できない。それでも確認するのは、届いている写真を上げ直さないため（Pi の上りは
        細く、再送は 5 分ごとに回る）。
        """
        try:
            response = requests.get(
                f"{self.api_url}/v2/photos/{photo_id}/metadata", timeout=10
            )
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Could not check backend for {photo_id}: {e}")
            return None
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        self.logger.warning(
            f"Unexpected status {response.status_code} checking backend for {photo_id}"
        )
        return None

    def reconcile_unsent(self, deadline_seconds=None):
        """未送信マークを API と突き合わせ、届いていないものを送る.

        deadline_seconds を渡すと、次の 1 件に進むかの判定に使う。処理中の 1 件は
        中断しないので、halt の遅れはこれに送信のタイムアウト（最大 40 秒）が乗る。
        返り値は残った未送信の件数。
        """
        with self.unsent_lock:
            return self._reconcile_unsent_locked(deadline_seconds)

    def _reconcile_unsent_locked(self, deadline_seconds):
        started = time.monotonic()
        for filename in self.list_unsent():
            if (
                deadline_seconds is not None
                and time.monotonic() - started >= deadline_seconds
            ):
                self.logger.warning("Reconcile deadline reached; leaving the rest")
                break
            self._upload_if_missing_locked(filename, require_mark=True)

        remaining = self.list_unsent()
        self._warn_if_stale(remaining)
        return len(remaining)

    def upload_if_missing(self, filename):
        """API に無ければ送る。手動再送もここを通す.

        存在確認と送信と印の削除は 1 つのロックの中で実施する。別々にすると、定期ループと
        手動再送が同時に「まだ届いていない」と判断して二重送信になる。
        返り値: already / sent / unknown（疎通しない）/ failed / missing_file

        印が無くても送る（require_mark を渡さない）。撮り直しで破棄した写真を後から
        救う手段がここだけなので、印の有無を送るかの条件にしない。
        """
        with self.unsent_lock:
            return self._upload_if_missing_locked(filename)

    def _upload_if_missing_locked(self, filename, require_mark=False):
        photo_id = os.path.splitext(filename)[0]
        exists = self._photo_exists_on_backend(photo_id)
        if exists is None:
            # 届いているか分からない。API は冪等なので送っても壊れないが、疎通が
            # 怪しいときに大きな本体を投げても通らない。次の周回に回す
            return "unknown"
        if exists:
            self.logger.info(f"Photo {photo_id} already on backend; clearing mark")
            self._clear_unsent(filename)
            return "already"

        filepath = os.path.join(self.photos_dir, filename)
        if not os.path.exists(filepath):
            self.logger.error(
                f"Unsent photo {filename} is missing from {self.photos_dir}; "
                "clearing mark (this day's record cannot be recovered)"
            )
            self._clear_unsent(filename)
            return "missing_file"

        # 存在確認は最大 10 秒かかる。その間に UI が撮り直しで破棄していることがあるので、
        # 送る直前に印を見直す。⚠️ ここを通った後の破棄には間に合わない
        # ＝送信中の 1 件だけは、捨てても API に載る
        if require_mark and not self._is_marked_unsent(filename):
            self.logger.info(f"{filename} was discarded while checking; not sending")
            return "discarded"

        # 撮影日はファイル名から取る。当日中に送れていれば API の受信時刻と同じ日に
        # なるので、正常系と同じ日付に揃う
        captured_date = self._captured_date_from_filename(filename)
        if self.send_to_backend(filepath, captured_date=captured_date):
            self.logger.info(f"Sent {filename} for {captured_date}")
            self._clear_unsent(filename)
            return "sent"
        return "failed"

    def _captured_date_from_filename(self, filename):
        """photo_YYYYMMDD_HHMMSS.jpg から "YYYY-MM-DD" を取り出す（取れなければ None）."""
        match = re.match(r"^photo_(\d{4})(\d{2})(\d{2})_\d{6}\.jpg$", filename)
        if not match:
            self.logger.warning(f"Cannot derive captured date from {filename}")
            return None
        return "-".join(match.groups())

    def _warn_if_stale(self, remaining):
        """長く残っている未送信をログに立てる（気づけないまま欠測するのを防ぐ）.

        ⚠️ ここだけは経過時間を壁時計で測る。マークは halt をまたいで残るので、
        プロセス内でしか続かない monotonic では測れない。代わりに NTP 同期後だけ
        判定する（未同期のうちは fake-hwclock の復元値で数時間ずれる）。
        """
        if not self._is_clock_synced():
            return
        now = time.time()
        for filename in remaining:
            path = os.path.join(self.unsent_dir, filename)
            try:
                age = now - os.path.getmtime(path)
            except OSError:
                continue
            if age >= self.unsent_stale_seconds:
                self.logger.error(
                    f"Photo {filename} has been unsent for {int(age / 3600)}h "
                    "— the record for that day is missing"
                )

    def _unsent_retry_loop(self):
        """疎通したときに未送信を送るループ."""
        while not self.stop_unsent_retry:
            try:
                self.reconcile_unsent()
            except Exception as e:
                self.logger.error(f"Error in unsent retry loop: {e}")
            time.sleep(self.unsent_retry_interval)

    def _start_unsent_retry_monitor(self):
        self.unsent_retry_thread = threading.Thread(
            target=self._unsent_retry_loop, daemon=True
        )
        self.unsent_retry_thread.start()

    def _get_cpu_temperature(self):
        """Raspberry Pi CPU温度を取得."""
        try:
            import subprocess

            result = subprocess.run(
                ["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                # 出力例: "temp=65.0'C"
                temp_str = result.stdout.strip()
                if "temp=" in temp_str:
                    temp_value = temp_str.split("=")[1].replace("'C", "")
                    return float(temp_value)

            self.logger.warning(f"vcgencmd failed: {result.stderr}")
            return 0.0

        except subprocess.TimeoutExpired:
            self.logger.warning("CPU temperature check timeout")
            return 0.0
        except FileNotFoundError:
            # vcgencmd not available (非Raspberry Pi環境)
            self.logger.debug("vcgencmd not found, thermal monitoring disabled")
            return 0.0
        except Exception as e:
            self.logger.warning(f"Failed to get CPU temperature: {e}")
            return 0.0

    def _thermal_monitor_loop(self):
        """温度監視とスロットリング制御ループ."""
        self.logger.info("🔥 Thermal monitor started")

        while not self.stop_thermal_monitor:
            try:
                # CPU温度取得
                temp = self._get_cpu_temperature()
                self.cpu_temperature = temp

                if temp == 0.0:
                    # 温度取得不可能な場合は監視無効化
                    time.sleep(self.THERMAL_MONITOR_INTERVAL)
                    continue

                # 前の制御レベルを保存
                prev_level = self.thermal_throttle_level

                # 温度に基づく制御レベル決定
                if temp >= self.THERMAL_HEAVY_THROTTLE:
                    self.thermal_throttle_level = 2  # 重度制御
                elif temp >= self.THERMAL_LIGHT_THROTTLE:
                    self.thermal_throttle_level = 1  # 軽度制御
                elif temp <= self.THERMAL_RECOVERY:
                    self.thermal_throttle_level = 0  # 制御解除
                # 中間温度では現在のレベルを維持（ヒステリシス）

                # 制御レベル変更時のログ出力
                if prev_level != self.thermal_throttle_level:
                    level_names = ["正常動作", "軽度制御", "重度制御"]
                    self.logger.warning(
                        f"🔥 Thermal control level changed: {temp:.1f}°C → "
                        f"{level_names[self.thermal_throttle_level]} (Level {self.thermal_throttle_level})"
                    )

                    if self.thermal_throttle_level == 1:
                        self.logger.info("  - Motion detection interval: 0.5s → 2.0s")
                    elif self.thermal_throttle_level == 2:
                        self.logger.info("  - Motion detection interval: 0.5s → 5.0s")
                        self.logger.info("  - AI detection: Paused")
                    elif self.thermal_throttle_level == 0:
                        self.logger.info("  - All functions restored to normal")

                # 正常範囲外の場合のみログ出力
                if temp > self.THERMAL_LIGHT_THROTTLE:
                    self.logger.warning(
                        f"🔥 CPU temperature: {temp:.1f}°C (Level {self.thermal_throttle_level})"
                    )

                # 設定可能な間隔で監視
                time.sleep(self.THERMAL_MONITOR_INTERVAL)

            except Exception as e:
                self.logger.error(f"Error in thermal monitor: {e}")
                time.sleep(self.THERMAL_MONITOR_INTERVAL)

        self.logger.info("🔥 Thermal monitor stopped")

    def _periodic_resource_cleanup(self):
        """Periodic resource cleanup to prevent memory leaks during long-term operation."""
        try:
            current_time = time.time()
            self.logger.info("🧹 Starting periodic resource cleanup...")

            # 1. PIR detection history cleanup
            cutoff_time = current_time - self.max_pir_history_age
            initial_count = len(self.pir_detections)
            self.pir_detections = [t for t in self.pir_detections if t > cutoff_time]
            removed_count = initial_count - len(self.pir_detections)

            if removed_count > 0:
                self.logger.info(
                    f"Cleaned up {removed_count} old PIR detection records"
                )

            # 4. Memory usage logging (if psutil is available)
            try:
                import psutil

                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                self.logger.info(f"Current memory usage: {memory_mb:.1f} MB")

                if memory_mb > 500:  # Log if memory usage > 500MB
                    self.logger.warning(
                        f"High memory usage detected: {memory_mb:.1f} MB"
                    )

            except ImportError:
                self.logger.debug("psutil not available, skipping memory usage logging")
            except Exception as e:
                self.logger.debug(f"Error checking memory usage: {e}")

            self.last_resource_cleanup = current_time
            self.logger.info("✅ Periodic resource cleanup completed")

            # Schedule next cleanup
            self._schedule_next_resource_cleanup()

        except Exception as e:
            self.logger.error(f"Error during periodic resource cleanup: {e}")
            # Ensure next cleanup is scheduled even if current one fails
            self._schedule_next_resource_cleanup()

    def _schedule_next_resource_cleanup(self):
        """Schedule the next periodic resource cleanup."""
        try:
            if self.resource_cleanup_timer:
                self.resource_cleanup_timer.cancel()

            self.resource_cleanup_timer = threading.Timer(
                self.resource_cleanup_interval, self._periodic_resource_cleanup
            )
            self.resource_cleanup_timer.daemon = True
            self.resource_cleanup_timer.start()

            self.logger.debug(
                f"Next resource cleanup scheduled in {self.resource_cleanup_interval}s"
            )

        except Exception as e:
            self.logger.error(f"Error scheduling next resource cleanup: {e}")

    def _start_periodic_resource_cleanup(self):
        """Start the periodic resource cleanup system."""
        self.logger.info(
            f"🧹 Starting periodic resource cleanup (interval: {self.resource_cleanup_interval}s)"
        )
        self._schedule_next_resource_cleanup()

    def cleanup_resources(self):
        """Clean up all resources before service shutdown."""
        self.logger.info("🧹 Starting camera service resource cleanup...")

        try:
            # Stop PIR monitoring
            if self._pir_monitoring_stop_event:
                self._pir_monitoring_stop_event.set()
                if (
                    hasattr(self, "pir_monitoring_thread")
                    and self.pir_monitoring_thread.is_alive()
                ):
                    self.pir_monitoring_thread.join(timeout=5)
                    self.logger.info("✅ PIR monitor thread stopped")

            # Stop thermal monitoring
            self.stop_thermal_monitor = True
            if self.thermal_monitor_thread and self.thermal_monitor_thread.is_alive():
                self.thermal_monitor_thread.join(timeout=5)
                self.logger.info("✅ Thermal monitor thread stopped")

            # Cancel all timers
            with self.display_state_lock:
                if self.display_off_timer:
                    self.display_off_timer.cancel()
                    self.display_off_timer = None
                    self.logger.info("✅ Display off timer cancelled")

                if self.camera_active_timer:
                    self.camera_active_timer.cancel()
                    self.camera_active_timer = None
                    self.logger.info("✅ Camera active timer cancelled")

                if self.resource_cleanup_timer:
                    self.resource_cleanup_timer.cancel()
                    self.resource_cleanup_timer = None
                    self.logger.info("✅ Resource cleanup timer cancelled")

            # Clean shutdown of display and Chromium processes
            if self.display_state != "off":
                self.logger.info("🔄 Turning off display for clean shutdown...")
                success = self._terminate_chromium_processes(graceful_timeout=5)
                if success:
                    self.logger.info("✅ Chromium processes terminated for shutdown")
                else:
                    self.logger.warning(
                        "⚠️ Some Chromium processes may still be running"
                    )

                # Turn off display
                try:
                    if self.backlight_device:
                        powered_off = self._write_backlight("bl_power", 1)
                        dimmed = self._write_backlight("brightness", 0)
                        if powered_off and dimmed:
                            self.logger.info("✅ Display powered off for shutdown")
                        else:
                            self.logger.warning(
                                "⚠️ Display may still be lit; backlight write failed"
                            )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to turn off display during shutdown: {e}"
                    )

                self.display_state = "off"

            # Release camera resources
            if hasattr(self, "cap") and self.cap is not None:
                try:
                    self.cap.release()
                    self.logger.info("✅ OpenCV camera released")
                except Exception as e:
                    self.logger.warning(f"Failed to release OpenCV camera: {e}")

            if hasattr(self, "picamera2") and self.picamera2 is not None:
                try:
                    self.picamera2.stop()
                    self.picamera2.close()
                    self.logger.info("✅ Picamera2 resources released")
                except Exception as e:
                    self.logger.warning(f"Failed to release Picamera2: {e}")

            self.logger.info("✅ Camera service cleanup completed successfully")

        except Exception as e:
            self.logger.error(f"❌ Error during resource cleanup: {e}")
            raise

    def _start_thermal_monitor(self):
        """温度監視バックグラウンドタスク開始."""
        self.thermal_monitor_thread = threading.Thread(
            target=self._thermal_monitor_loop, daemon=True
        )
        self.thermal_monitor_thread.start()
        self.logger.info("🔥 Thermal monitoring enabled")

    def _perform_shutdown(self, reason="requested"):
        """Pi をグレースフルにシャットダウン（halt）する。

        AUTO_SHUTDOWN_ENABLED=true のときのみ実行。HA 側は ping 不応答を確認してから
        プラグを切る運用（halt 完了後に de-power）なので、ここは halt するだけでよい。
        """
        if not self.auto_shutdown_enabled:
            self.logger.info(
                f"⏻ Shutdown requested ({reason}) but AUTO_SHUTDOWN_ENABLED!=true — ignoring"
            )
            return False
        if self._shutdown_in_progress:
            return True
        self._shutdown_in_progress = True
        self.logger.warning(f"⏻ Initiating graceful shutdown (reason: {reason})")

        def _do_shutdown():
            # UI が完了表示を出せるよう数秒猶予を置いてから halt する。
            # systemd がサービス停止を経て安全に halt（SD 書き込み完了）する。
            try:
                time.sleep(3)
                # 落ちる前に送り残しを片付ける。halt が遅れるのは最大でも数十秒で、
                # HA は ping 不応答を見てからプラグを切るため待たされて困るものはない。
                # 20:00 の cutoff は UI が送っている最中でも落とすが、API が冪等に
                # なったので割り込んで送っても重複レコードにはならない
                try:
                    self.reconcile_unsent(deadline_seconds=10)
                except Exception as e:
                    self.logger.error(f"Reconcile before shutdown failed: {e}")
                subprocess.run(["sudo", "shutdown", "-h", "now"], check=False)
            except Exception as e:
                self.logger.error(f"Shutdown command failed: {e}")
                self._shutdown_in_progress = False

        threading.Thread(target=_do_shutdown, daemon=True).start()
        return True

    @staticmethod
    def _parse_hhmm(value, default):
        """\"HH:MM\" を (hour, minute) にパースする。不正値は default にフォールバック。"""
        try:
            hour, minute = value.strip().split(":")
            return int(hour), int(minute)
        except (ValueError, AttributeError):
            return default

    def _uptime_seconds(self):
        """システム起動からの経過秒を返す（壁時計に依らない）。

        ⚠️ サービス起動からの monotonic では測らない。ヘルスモニタが /stream の異常で
        coordinate-camera.service を restart する（systemd/scripts/kiosk-health-monitor.sh）
        ため、サービス基準だとバックストップのタイマーが巻き戻って規定時間で halt しない。
        /proc が無い環境（ローカル開発の macOS 等）だけサービス起動基準にフォールバックする。
        """
        try:
            with open("/proc/uptime") as f:
                return float(f.read().split()[0])
        except (OSError, ValueError, IndexError):
            return time.monotonic() - self.service_start_monotonic

    def _clock_synced_this_boot(self):
        """この boot で一度でも NTP 同期したかを返す。

        ⚠️ プロセス内の latch だけに頼らない。ヘルスモニタがサービスを restart すると latch は
        巻き戻る一方、経過はシステム起動基準（_uptime_seconds）で残る。同期後に NTP を見失った
        Pi（timedatectl が no を返す）を「一度も同期していない」と誤認して昼間に halt しうる。
        systemd-timesyncd のフラグは /run（tmpfs）にあり boot ごとに消えるので、
        「一度も同期していない」と「同期後に見失った」を再起動をまたいで区別できる。
        """
        return os.path.exists(self.clock_synced_flag_path)

    def _is_clock_synced(self):
        """システムクロックが NTP 同期済かを返す（True / False / 判定不能なら None）。

        RTC バッテリーが無いため起動直後は fake-hwclock が前回 halt 時刻（≒前夜 20:00）を
        復元しており壁時計は信用できない。NTP 同期が済むまで毎日 cutoff の判定を保留する。

        ⚠️ timedatectl が答えないケースを False（未同期）に丸めない。未同期バックストップは
        「未同期を実際に観測した」ときだけ発火させる。同期済かどうかを判定できない周回で
        halt すると、稼働中の Pi を落とす。
        """
        try:
            result = subprocess.run(
                ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        if value == "yes":
            return True
        if value == "no":
            return False
        return None

    def _scheduled_shutdown_loop(self):
        """点きっぱなしの Pi を halt するループ（最後の砦）。

        撮影の有無は見ない。cutoff を過ぎていれば halt する。撮影が済んだ日は通常
        それ以前に UI の POST /shutdown で落ちているので、ここが拾うのは落ち残り。
        ⚠️ 「撮影済なら落とさない」に寄せない。アップロードが失敗した日に
        落ちる条件を失い、点きっぱなしが常態化する。

        発火源は 3 つ:
          ① 壁時計が毎日 cutoff（既定 20:00 JST）を過ぎたら halt。NTP 同期後のみ・JST 固定で判定
          ② NTP が一度も同期しないまま max_unsynced_uptime_seconds を超えたら halt。
             ① は同期するまで判定を保留するので、同期しない日はここが唯一の実用的な砦になる。
             未同期を実際に観測した周回だけ数える（_is_clock_synced が None の周回は見送る）
          ③ 最終バックストップ: max_uptime_seconds を超えたら壁時計に依らず halt（無期限点灯の防止）
        撮影完了時の即時 halt は UI からの POST /shutdown が担うため、ここは関与しない。

        ⚠️ ① の同期判定は boot 単位で latch する（一度同期したら以後は壁時計を信用する）。
        同期後に NTPSynchronized が no に転んでも cutoff を止めない。数時間のドリフトは
        cutoff の判定に影響しないのに対し、判定を止めると再び点きっぱなしの窓が開く。
        """
        if not self.auto_shutdown_enabled:
            self.logger.info(
                "⏻ Scheduled shutdown monitor disabled (AUTO_SHUTDOWN_ENABLED!=true)"
            )
            return
        self.logger.info(
            "⏻ Scheduled shutdown monitor started "
            f"(daily cutoff: {self.daily_shutdown_hour:02d}:{self.daily_shutdown_minute:02d} JST, "
            f"max uptime: {self.max_uptime_seconds}s, "
            f"max unsynced uptime: {self.max_unsynced_uptime_seconds}s)"
        )
        while not self.stop_shutdown_monitor:
            try:
                uptime = self._uptime_seconds()
                if uptime >= self.max_uptime_seconds:
                    self.logger.warning(
                        f"⏻ Uptime {int(uptime)}s >= {self.max_uptime_seconds}s "
                        "— shutting down (max-uptime backstop)"
                    )
                    self._perform_shutdown(reason="max-uptime backstop")
                    return
                synced = self._is_clock_synced()
                if not self._clock_ever_synced and (
                    synced or self._clock_synced_this_boot()
                ):
                    self._clock_ever_synced = True
                    self.logger.info(
                        f"⏻ Clock synced after {int(uptime)}s — daily cutoff now evaluated"
                    )
                if self._clock_ever_synced:
                    now = datetime.now(ZoneInfo("Asia/Tokyo"))
                    if (now.hour, now.minute) >= (
                        self.daily_shutdown_hour,
                        self.daily_shutdown_minute,
                    ):
                        self.logger.warning(
                            "⏻ Past daily cutoff "
                            f"{self.daily_shutdown_hour:02d}:{self.daily_shutdown_minute:02d} "
                            f"(now {now:%H:%M} JST) — shutting down"
                        )
                        self._perform_shutdown(reason="daily cutoff")
                        return
                elif synced is False and uptime >= self.max_unsynced_uptime_seconds:
                    self.logger.warning(
                        f"⏻ Clock never synced for {int(uptime)}s "
                        f">= {self.max_unsynced_uptime_seconds}s "
                        "— shutting down (unsynced-clock backstop)"
                    )
                    self._perform_shutdown(reason="unsynced-clock backstop")
                    return
                time.sleep(60)
            except Exception as e:
                self.logger.error(f"Error in scheduled shutdown monitor: {e}")
                time.sleep(60)

    def _start_shutdown_monitor(self):
        """スケジュール自動シャットダウン監視スレッドを開始する."""
        self.shutdown_monitor_thread = threading.Thread(
            target=self._scheduled_shutdown_loop, daemon=True
        )
        self.shutdown_monitor_thread.start()

    def _terminate_chromium_processes(self, graceful_timeout=3):
        """Enhanced Chromium process termination with verification."""
        try:
            # Check if any Chromium processes exist
            check_result = subprocess.run(
                ["pgrep", "-f", "chromium.*touchscreen"], capture_output=True, timeout=5
            )

            if check_result.returncode != 0:
                self.logger.info("No existing Chromium touchscreen processes found")
                return True

            process_count = len(check_result.stdout.decode().strip().split("\n"))
            self.logger.info(f"Found {process_count} Chromium touchscreen processes")

            # Step 1: Graceful termination (SIGTERM)
            self.logger.info("Sending SIGTERM to Chromium processes...")
            subprocess.run(
                ["pkill", "-TERM", "-f", "chromium.*touchscreen"],
                capture_output=True,
                timeout=5,
            )

            # Step 2: Wait for graceful shutdown
            for i in range(graceful_timeout):
                time.sleep(1)
                check_result = subprocess.run(
                    ["pgrep", "-f", "chromium.*touchscreen"],
                    capture_output=True,
                    timeout=5,
                )
                if check_result.returncode != 0:
                    self.logger.info(
                        f"✅ Chromium processes terminated gracefully ({i+1}s)"
                    )
                    return True

            # Step 3: Force termination (SIGKILL) if graceful failed
            self.logger.warning("Graceful termination timeout, using force kill...")
            subprocess.run(
                ["pkill", "-KILL", "-f", "chromium.*touchscreen"],
                capture_output=True,
                timeout=5,
            )

            # Final verification
            time.sleep(0.5)
            check_result = subprocess.run(
                ["pgrep", "-f", "chromium.*touchscreen"], capture_output=True, timeout=5
            )

            if check_result.returncode == 0:
                self.logger.error("❌ Failed to terminate some Chromium processes")
                return False
            else:
                self.logger.info("✅ All Chromium processes terminated successfully")
                return True

        except Exception as e:
            self.logger.error(f"Error during Chromium termination: {e}")
            return False

    def _launch_chromium_with_retry(self, max_retries=3):
        """Launch Chromium with retry mechanism."""
        url = "http://localhost:3000/touchscreen"

        for attempt in range(max_retries):
            try:
                self.logger.info(
                    f"Launching Chromium (attempt {attempt + 1}/{max_retries})..."
                )

                chromium_env = os.environ.copy()
                chromium_env.update({"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"})

                process = subprocess.Popen(
                    [
                        "/usr/bin/chromium-browser",
                        "--kiosk",
                        "--no-first-run",
                        "--disable-infobars",
                        "--disable-session-crashed-bubble",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-features=TranslateUI",
                        "--disable-translate",
                        "--start-fullscreen",
                        "--disable-web-security",
                        "--fast-start",
                        "--user-data-dir=/tmp/chromium-touchscreen",
                        url,
                    ],
                    env=chromium_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                # Give process time to initialize
                time.sleep(1.5)

                # Check if process is still running
                if process.poll() is None:
                    self.logger.info(
                        f"✅ Chromium launched successfully (PID: {process.pid})"
                    )
                    return True
                else:
                    self.logger.warning(
                        f"Chromium process exited immediately (attempt {attempt + 1})"
                    )

            except Exception as e:
                self.logger.error(
                    f"Error launching Chromium (attempt {attempt + 1}): {e}"
                )

            if attempt < max_retries - 1:
                self.logger.info("Retrying Chromium launch in 1 second...")
                time.sleep(1)

        self.logger.error(f"Failed to launch Chromium after {max_retries} attempts")
        return False

    def _verify_chromium_startup(self, timeout=5):
        """Verify that Chromium process is running and responsive."""
        try:
            for i in range(timeout):
                # Check if process exists
                check_result = subprocess.run(
                    ["pgrep", "-f", "chromium.*touchscreen"],
                    capture_output=True,
                    timeout=3,
                )

                if check_result.returncode == 0:
                    process_count = len(
                        check_result.stdout.decode().strip().split("\n")
                    )
                    self.logger.info(
                        f"✅ Chromium startup verified ({process_count} processes)"
                    )
                    return True

                time.sleep(1)

            self.logger.warning("❌ Chromium startup verification failed")
            return False

        except Exception as e:
            self.logger.error(f"Error verifying Chromium startup: {e}")
            return False

    def _update_pir_activity(self):
        """PIR 活動でディスプレイ消灯タイマーをリセットする."""
        self.logger.debug("PIR activity detected")
        # PIR 検知時は常にディスプレイタイマーをリセット
        if self.display_state == "on" and self.display_off_timer:
            self.logger.info("PIR activity detected - resetting display timer")
            self.display_off_timer.cancel()
            self._start_display_off_timer()

    def _start_display_off_timer(self):
        """Start 30-second display off timer."""
        if self.display_off_timer:
            self.display_off_timer.cancel()
            self.display_off_timer = None

        # Start fixed 30-second timer
        self.display_off_timer = threading.Timer(
            self.display_timeout, self._handle_display_timeout
        )
        self.display_off_timer.start()
        self.logger.info(f"Display will turn off in {self.display_timeout} seconds")

    def _handle_display_timeout(self):
        """Handle display timeout - turn off display after 30 seconds."""
        with self.display_state_lock:
            if self.display_state == "on":
                self.logger.info("Display timeout reached - turning off display")
                self.display_state = "off"
                # Turn off display in background
                threading.Thread(
                    target=self._turn_off_display_async, daemon=True
                ).start()

    def _turn_off_display_async(self):
        """Asynchronously turn off display."""
        try:
            success = self.turn_off_display()
            if not success:
                self.logger.error("Failed to turn off display")
        except Exception as e:
            self.logger.error(f"Error in async display turn off: {e}")

    def turn_on_display(self):
        """Turn on display using display-brightness.sh script."""
        try:
            # Check and update display state
            with self.display_state_lock:
                if self.display_state == "on":
                    self.logger.info("Display already on")
                    return True

                self.display_state = "on"

            self.logger.info("Turning on display using display-brightness.sh...")

            # シンプルにdisplay-brightness.shを使用
            display_script = os.path.expanduser(
                os.environ.get(
                    "DISPLAY_BRIGHTNESS_SCRIPT",
                    "/home/pi/coordinate-recorder/scripts/display-brightness.sh",
                )
            )

            if os.path.exists(display_script):
                helper_script_py = os.path.join(
                    os.path.dirname(display_script), "display-power-helper.py"
                )

                if os.path.exists(helper_script_py):
                    self.logger.info(f"Using power helper: {helper_script_py}")
                    result = subprocess.run(
                        [helper_script_py, "on"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                else:
                    self.logger.info(f"Using display script: {display_script}")
                    result = subprocess.run(
                        ["bash", display_script, "power-on"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                if result.returncode == 0:
                    self.logger.info(
                        "✅ Display turned on successfully via display-brightness.sh"
                    )
                    self.logger.info(f"Script output: {result.stdout.strip()}")

                    # Start 30-second timer
                    self._start_display_off_timer()
                    return True
                else:
                    self.logger.error(f"❌ Display script failed: {result.stderr}")
                    with self.display_state_lock:
                        self.display_state = "off"
                    return False
            else:
                self.logger.error(f"Display script not found: {display_script}")
                return False

        except Exception as e:
            self.logger.error(f"Error turning on display: {e}")
            with self.display_state_lock:
                self.display_state = "off"
            return False

    def turn_off_display(self):
        """Turn off display automatically after timeout using display-brightness.sh."""
        try:
            self.logger.info("Turning off display using display-brightness.sh...")
            import subprocess
            from pathlib import Path

            # Get project root path
            project_root = Path(__file__).parent.parent
            display_script = project_root / "scripts" / "display-brightness.sh"

            # Use display-brightness.sh for unified display control
            if display_script.exists():
                helper_script_py = project_root / "scripts" / "display-power-helper.py"

                if helper_script_py.exists():
                    self.logger.info(f"Using power helper: {helper_script_py}")
                    cmd = [str(helper_script_py), "off"]
                    self.logger.info(f"Executing command: {' '.join(cmd)}")
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                else:
                    self.logger.info(f"Using display script: {display_script}")
                    cmd = ["bash", str(display_script), "power-off"]
                    self.logger.info(f"Executing command: {' '.join(cmd)}")
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                if result.returncode == 0:
                    self.logger.info(
                        "✅ Display turned off successfully via display-brightness.sh"
                    )
                    self.logger.info(f"Script output: {result.stdout.strip()}")
                    # 実際のハードウェア状態を確認
                    self.logger.info("Verifying hardware state after power-off...")
                    verify_result = subprocess.run(
                        ["bash", str(display_script), "status"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if verify_result.returncode == 0:
                        self.logger.info(
                            f"Hardware state after OFF: {verify_result.stdout.strip()}"
                        )
                else:
                    self.logger.error(
                        f"❌ Display script failed: {result.stderr.strip()}"
                    )
                    return False
            else:
                self.logger.error(f"Display script not found: {display_script}")
                # Fallback to direct backlight control
                if self.backlight_device:
                    powered_off = self._write_backlight("bl_power", 1)
                    dimmed = self._write_backlight("brightness", 0)
                    if not (powered_off and dimmed):
                        return False
                else:
                    self.logger.warning(
                        "No backlight device available for display control"
                    )
                    return False

            self.logger.info(
                "Display turned off successfully - brightness=0, bl_power=1"
            )

            return True

        except Exception as e:
            self.logger.error(f"Failed to turn off display: {e}")
            return False

    def _validate_environment_variables(self):
        """Validate environment variables with range checks."""
        env_validations = {
            "THERMAL_MONITOR_INTERVAL": (1.0, 300.0, float),
            "THERMAL_LIGHT_THROTTLE": (60.0, 90.0, float),
            "THERMAL_HEAVY_THROTTLE": (70.0, 95.0, float),
            "THERMAL_RECOVERY": (50.0, 80.0, float),
            "PIR_GPIO_PIN": (1, 40, int),
            "PIR_DETECTION_THRESHOLD": (1, 10, int),
            "PIR_DETECTION_WINDOW": (1, 60, int),
            "CAMERA_ACTIVE_DURATION": (60, 3600, int),
            "DISPLAY_ON_DURATION": (30, 1800, int),
            "STREAMING_FPS": (1.0, 30.0, float),
            "CAMERA_AWB_RED_GAIN": (0.5, 3.0, float),
            "CAMERA_AWB_BLUE_GAIN": (0.5, 3.0, float),
        }

        validation_errors = []

        for env_var, (min_val, max_val, var_type) in env_validations.items():
            env_value = os.environ.get(env_var)
            if env_value is not None:
                try:
                    parsed_value = var_type(env_value)
                    if not (min_val <= parsed_value <= max_val):
                        validation_errors.append(
                            f"{env_var}={env_value} is out of range [{min_val}, {max_val}]"
                        )
                    else:
                        self.logger.info(f"✅ {env_var}={parsed_value} (valid)")
                except ValueError:
                    validation_errors.append(
                        f"{env_var}={env_value} is not a valid {var_type.__name__}"
                    )

        # Boolean validations
        bool_vars = [
            "PIR_ENABLED",
            "PIR_SIMULATION_MODE",
            "ENABLE_DISPLAY_ON_DETECTION",
            "CAMERA_VFLIP",
            "CAMERA_HFLIP",
        ]

        for env_var in bool_vars:
            env_value = os.environ.get(env_var)
            if env_value is not None and env_value.lower() not in ["true", "false"]:
                validation_errors.append(
                    f"{env_var}={env_value} must be 'true' or 'false'"
                )
            elif env_value is not None:
                self.logger.info(f"✅ {env_var}={env_value.lower()} (valid)")

        # Camera mode validation
        camera_mode = os.environ.get("CAMERA_MODE", "hardware")
        valid_modes = ["hardware", "simulation"]
        if camera_mode not in valid_modes:
            validation_errors.append(
                f"CAMERA_MODE={camera_mode} must be one of {valid_modes}"
            )
        else:
            self.logger.info(f"✅ CAMERA_MODE={camera_mode} (valid)")

        if validation_errors:
            error_msg = "Environment variable validation failed:\n" + "\n".join(
                validation_errors
            )
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        self.logger.info("✅ All environment variables validated successfully")

    def __del__(self):
        """Cleanup resources when CameraService is destroyed."""
        try:
            self._cleanup_timers()
            # 解放処理はどれが失敗しても残りを続ける。ここで送出すると後続の解放が飛ぶ
            if hasattr(self, "picamera2") and self.picamera2 is not None:
                try:
                    self.picamera2.stop()
                    self.picamera2.close()
                except Exception:  # noqa: S110
                    pass
            if hasattr(self, "cap") and self.cap is not None:
                try:
                    self.cap.release()
                except Exception:  # noqa: S110
                    pass
            self.logger.info("✅ CameraService resources cleaned up")
        except Exception:  # noqa: S110
            pass

    def _cleanup_timers(self):
        """Clean up all active timers safely."""
        timer_attributes = [
            "display_off_timer",
            "camera_active_timer",
            "thermal_monitor_timer",
        ]

        for timer_attr in timer_attributes:
            timer = getattr(self, timer_attr, None)
            if timer and hasattr(timer, "cancel"):
                try:
                    timer.cancel()
                    self.logger.info(f"✅ Cancelled timer: {timer_attr}")
                except Exception as e:
                    self.logger.warning(f"Failed to cancel {timer_attr}: {e}")
                finally:
                    setattr(self, timer_attr, None)

    # Backlight Device Detection
    def _write_backlight(self, attr, value):
        """バックライトの sysfs 属性へ書き込む。成否を bool で返す。

        sudo は使わない。`deploy/udev/99-coordinate-backlight.rules` と Raspberry Pi OS
        標準の `60-backlight.rules` が `brightness`・`bl_power` を video グループ書き込み
        可にしており、サービスは `SupplementaryGroups=video` で動く。
        書けないときは黙って諦めず error を出す。権限が失われると画面が制御不能になり、
        以前は capture_output で握りつぶしていて気づけなかった。
        """
        # 属性ごとに権限を与えている rule が違う。誤った方を案内しないよう出し分ける。
        rules = {
            "brightness": "Raspberry Pi OS 標準の /usr/lib/udev/rules.d/60-backlight.rules",
            "bl_power": "deploy/udev/99-coordinate-backlight.rules",
        }
        path = f"{self.backlight_device}/{attr}"
        try:
            with open(path, "w") as f:
                f.write(f"{value}\n")
            return True
        except OSError as e:
            hint = rules.get(attr, "backlight の udev rule")
            self.logger.error(
                f"❌ Failed to write {value} to {path}: {e}. {hint} の適用を確認すること"
            )
            return False

    def _detect_backlight_device(self):
        """Auto-detect backlight device path for display control."""
        import glob

        # Try to find available backlight devices
        backlight_devices = []
        try:
            for device_path in glob.glob("/sys/class/backlight/*/bl_power"):
                device_dir = os.path.dirname(device_path)
                if os.path.exists(device_dir + "/brightness"):
                    backlight_devices.append(device_dir)

            if not backlight_devices:
                self.logger.warning(
                    "No backlight devices found, display control may not work"
                )
                return None
            elif len(backlight_devices) == 1:
                device = backlight_devices[0]
                self.logger.info(f"Auto-detected backlight device: {device}")
                return device
            else:
                # Multiple devices found, prefer certain patterns
                for device in backlight_devices:
                    # Prefer devices with common Raspberry Pi patterns
                    if any(
                        pattern in device for pattern in ["11-0045", "10-0045", "rpi"]
                    ):
                        self.logger.info(
                            f"Selected backlight device: {device} (preferred pattern)"
                        )
                        return device

                # If no preferred pattern, use the first one
                device = backlight_devices[0]
                self.logger.info(
                    f"Selected backlight device: {device} (first available)"
                )
                self.logger.info(f"Available devices: {backlight_devices}")
                return device

        except Exception as e:
            self.logger.error(f"Error detecting backlight device: {e}")
            # Fallback to common Raspberry Pi paths
            fallback_devices = [
                "/sys/class/backlight/11-0045",
                "/sys/class/backlight/10-0045",
            ]
            for device in fallback_devices:
                if os.path.exists(device):
                    self.logger.info(f"Using fallback backlight device: {device}")
                    return device

            self.logger.warning("No backlight device found, display control disabled")
            return None

    # PIR Sensor Methods
    def _init_pir_sensor(self):
        """PIRセンサーを初期化."""
        if self.pir_simulation_mode:
            self.logger.info("PIR sensor initialized in simulation mode")
            return

        try:
            # gpiozeroライブラリとLGPIOFactoryをインポート
            from gpiozero import MotionSensor
            from gpiozero.pins.lgpio import LGPIOFactory

            self.logger.info(f"Initializing PIR sensor on GPIO pin {self.pir_gpio_pin}")

            # Pi 5対応：LGPIOFactory(chip=0)を明示的に指定
            lgpio_factory = LGPIOFactory(chip=0)
            self.pir_sensor = MotionSensor(self.pir_gpio_pin, pin_factory=lgpio_factory)
            self.pir_sensor.when_motion = self._on_pir_motion
            self.pir_sensor.when_no_motion = self._on_pir_no_motion

            self.logger.info("PIR sensor initialized successfully with LGPIOFactory")

            # PIRセンサーの継続監視を開始
            self._start_pir_monitoring()

        except ImportError as e:
            self.logger.warning(
                f"gpiozero or lgpio library not available: {e}, PIR sensor disabled"
            )
            self.logger.info(
                "Pi 5 環境の場合は './scripts/setup/setup-pi5-gpio.sh' を実行してください"
            )
            self.pir_enabled = False
        except PermissionError as e:
            self.logger.error(f"GPIO アクセス権限がありません: {e}")
            self.logger.info(
                "ユーザーが gpio グループに所属していることを確認してください"
            )
            self.logger.info("コマンド: sudo usermod -a -G gpio $USER")
            self.pir_enabled = False
        except Exception as e:
            error_msg = str(e).lower()
            if "chip not available" in error_msg or "gpiochip" in error_msg:
                self.logger.error(f"GPIO チップが利用できません: {e}")
                self.logger.info(
                    "Pi 5 の場合は lgpio ファクトリーが正しく設定されているか確認してください"
                )
            else:
                self.logger.error(f"PIR センサーの初期化に失敗: {e}")
            self.pir_enabled = False

    def _on_pir_motion(self):
        """PIRセンサーがモーションを検知した時のコールバック."""
        current_time = time.time()

        self.logger.info(
            f"PIR motion detected at {datetime.fromtimestamp(current_time)}"
        )

        # 検知履歴を更新
        self.pir_detections.append(current_time)

        # 古い検知履歴をクリーンアップ（detection_window外のものを削除）
        self.pir_detections = [
            t
            for t in self.pir_detections
            if current_time - t <= self.pir_detection_window
        ]

        # しきい値チェック（3秒以内に2回検知）。
        # 画面点灯は日次撮影の完了状態から独立させる（撮影済でも人が来たら
        # 画面を起こす・キオスク/タッチ UI 用途）。この PIR 経路自体は
        # capture_photo を呼ばない（撮影は touchscreen/API 起点）ため、点灯を撮影
        # 状態から切り離しても撮影の発火には影響しない。
        if len(self.pir_detections) >= self.pir_detection_threshold:
            self.logger.info(
                f"PIR detection threshold met: {len(self.pir_detections)} detections in {self.pir_detection_window}s"
            )

            # 在席が続く間はディスプレイ消灯タイマーをリセットして画面を点け続ける。
            self._update_pir_activity()

            # ディスプレイをONにする
            self.logger.info("Turning on display due to PIR detection...")
            success = self.turn_on_display()
            if success:
                self.last_display_time = current_time
            else:
                self.logger.error("Failed to turn on display for PIR detection")

    def _on_pir_no_motion(self):
        """PIRセンサーがモーション終了を検知した時のコールバック."""
        current_time = time.time()
        self.logger.info(f"PIR motion ended at {datetime.fromtimestamp(current_time)}")

        # モーション終了後に30秒タイマーを開始
        if self.display_state == "on":
            self.logger.info("Starting display off timer after motion ended")
            self._start_display_off_timer()

    # _restart_camera_service メソッドを削除（無限ループを防ぐため）

    def _launch_chromium_process(self):
        """Launch Chromium browser for touchscreen UI."""
        try:
            # First terminate any existing Chromium processes
            self._terminate_chromium_processes(graceful_timeout=2)

            # Launch new Chromium instance
            success = self._launch_chromium_with_retry(max_retries=3)
            if success:
                self._verify_chromium_startup(timeout=5)
        except Exception as e:
            self.logger.error(f"Error launching Chromium: {e}")

    def _is_daily_photo_completed(self):
        """1日1回撮影が完了しているかチェック（翌日午前7時リセット）."""
        now = datetime.now()

        # 午前7時基準での「今日」を計算
        current_day = get_effective_date(now, cutoff_hour=7)

        # 日付が変わった場合はリセット
        if self.last_photo_date != current_day:
            self.daily_photo_taken = False
            self.last_photo_date = current_day
            self.logger.info(f"Daily photo status reset for {current_day} (7AM-based)")

        # ローカルフラグが True の場合: キャッシュ有効中は即座に返す
        # キャッシュ期限切れなら API を再確認（GUI で写真削除された場合に同期）
        if self.daily_photo_taken:
            current_time = time.time()
            cache_valid = (
                self._capture_status_cache is not None
                and current_time - self._capture_status_cache_time
                < self._capture_status_cache_duration
            )
            if cache_valid:
                self.logger.debug("Local flag confirms: daily photo already taken")
                return True
            # キャッシュ期限切れ → API で再確認（写真削除の検出）
            return self._check_api_capture_status()

        # ローカルフラグが False の場合は API で確認（起動直後の同期用）
        return self._check_api_capture_status()

    def _check_api_capture_status(self):
        """API の /capture-required エンドポイントで撮影済状況を確認（キャッシュ付き）."""
        current_time = time.time()

        # キャッシュが有効な場合はキャッシュから返す
        if (
            self._capture_status_cache is not None
            and current_time - self._capture_status_cache_time
            < self._capture_status_cache_duration
        ):
            self.logger.debug(
                f"Using cached capture status: {self._capture_status_cache}"
            )
            return self._capture_status_cache

        # キャッシュが無効な場合は API を呼び出す
        try:
            response = requests.get(f"{self.api_url}/v2/capture-required", timeout=5)
            if response.status_code == 200:
                data = response.json()
                already_captured = data.get("already_captured", False)

                if already_captured:
                    self.logger.info("API confirms: Daily photo already captured")
                    self.daily_photo_taken = True
                    result = True
                else:
                    self.logger.info("API confirms: Daily photo capture required")
                    self.daily_photo_taken = False
                    result = False

                # キャッシュを更新
                self._capture_status_cache = result
                self._capture_status_cache_time = current_time
                return result
            else:
                self.logger.warning(
                    f"API capture-required check failed: {response.status_code}"
                )
                # API エラー時はローカル状態を使用
                return self.daily_photo_taken
        except Exception as e:
            self.logger.warning(f"Failed to check API capture status: {e}")
            # API アクセス失敗時はローカル状態を使用
            return self.daily_photo_taken

    def _mark_daily_photo_taken(self):
        """1日1回撮影を完了としてマーク."""
        now = datetime.now()
        self.daily_photo_taken = True
        self.last_photo_date = now.date()

        # キャッシュも撮影済に更新（API 問い合わせ前に正しい状態を返す）
        self._capture_status_cache = True
        self._capture_status_cache_time = time.time()

        self.logger.info(f"Daily photo marked as taken on {self.last_photo_date}")

        # 撮影完了後はスリープモードに戻る
        if self.current_mode == "active":
            if self.camera_active_timer:
                self.camera_active_timer.cancel()
            # TODO: Implement sleep mode transition
            self.logger.info("Should return to sleep mode after daily photo taken")

    def _start_pir_monitoring(self):
        """PIRセンサーの状態を定期的に監視してタイマーをリセット."""
        # スレッド停止用イベントを作成
        self._pir_monitoring_stop_event = threading.Event()

        def monitor_pir():
            self.logger.info("🕐 PIRセンサー継続監視を開始しました")

            while (
                self.pir_enabled
                and hasattr(self, "pir_sensor")
                and not self._pir_monitoring_stop_event.is_set()
            ):

                try:
                    # PIRセンサーが motion 状態かチェック
                    pir_is_active = False

                    # PIRセンサーアクセスをロックで保護
                    with self.pir_sensor_lock:
                        try:
                            # hasattr() もプロパティアクセスを行うため、
                            # RuntimeError をキャッチする必要がある
                            if hasattr(self.pir_sensor, "is_active"):
                                pir_is_active = self.pir_sensor.is_active
                        except RuntimeError as e:
                            if "deque mutated during iteration" in str(e):
                                # gpiozero のスレッドセーフでない問題を無視
                                self.logger.debug(
                                    f"PIR sensor read conflict (ignorable): {e}"
                                )
                                # エラー時はデフォルト値を使用
                                pir_is_active = False
                            else:
                                raise

                    if pir_is_active:
                        # PIR検知中 - display_state_lockで保護
                        # 画面点灯は日次撮影の完了状態から独立させる。
                        needs_display_on = False

                        with self.display_state_lock:
                            if self.display_state == "on" and self.display_off_timer:
                                self.logger.debug(
                                    "🔥 PIR still active - resetting display timer"
                                )
                                self.display_off_timer.cancel()
                                self._start_display_off_timer()
                            elif self.display_state == "off":
                                self.logger.info(
                                    "⏰ PIR active while display OFF - turning on display"
                                )
                                needs_display_on = True

                        # ロック外でディスプレイON（デッドロック回避）。
                        # turn_on_display が内部で off タイマーを開始するため二重開始しない。
                        if needs_display_on:
                            self.turn_on_display()

                        # 撮影済は長間隔でCPU負荷軽減、未撮影は短間隔で追従
                        sleep_time = 15 if self._is_daily_photo_completed() else 5
                    else:
                        # 非アクティブ時のポーリング間隔。短くすると PIR 検知〜点灯の
                        # 最大待ち時間が縮み、点灯のムラが減る（15s→5s・ の
                        # チューニング）。無人時に 3 倍の頻度で回るぶん CPU は微増。
                        sleep_time = 5

                except Exception as e:
                    # 詳細なエラー情報を出力
                    self.logger.error(f"PIR monitoring error: {e}", exc_info=True)
                    sleep_time = 10

                # イベント待機（停止可能）
                if self._pir_monitoring_stop_event.wait(sleep_time):
                    break

            self.logger.info("🌙 PIRセンサー継続監視を終了しました")

        # バックグラウンドスレッドで監視開始
        self.pir_monitoring_thread = threading.Thread(target=monitor_pir, daemon=True)
        self.pir_monitoring_thread.start()
        self.logger.info("🕐 PIRセンサー継続監視スレッドを開始しました")


# FastAPI app
app = FastAPI()

# 認証トークン（共有シークレット）。設定時のみ enforce する（未設定なら fail-open）。
# 配備は Pi の .env（CAMERA_API_TOKEN=...）に置き、リモート経路は Caddy が
# X-Camera-Token ヘッダで注入する。詳細は deploy/docs/camera-service-auth.md。
CAMERA_API_TOKEN = os.environ.get("CAMERA_API_TOKEN", "").strip()

# fail-open を無音にしない。未設定だと脆弱状態のまま起動するので、起動ログに警告を
# 出し（.env の消失・typo・再プロビジョニング時の設定漏れを検知可能に）、/health にも
# auth_enforced を載せて外形監視で拾えるようにする。
if not CAMERA_API_TOKEN:
    logging.getLogger(__name__).warning(
        "CAMERA_API_TOKEN 未設定: カメラサービスの認証は無効です（全リクエスト素通し）。"
        "deploy/docs/camera-service-auth.md の手順でトークンを設定してください。"
    )

# 認証を免除するパス。read-only な状態確認のみ（監視スクリプト・ヘルスチェック用）。
AUTH_EXEMPT_PATHS = frozenset({"/health", "/status"})

# 認証を免除する送信元。ローカルホスト = Pi 自身のキオスクブラウザ（信頼境界内）。
# キオスクは http://localhost:8001 に直アクセスするため、トークンなしで動作する。
AUTH_EXEMPT_HOSTS = frozenset({"127.0.0.1", "::1"})


@app.middleware("http")
async def require_camera_token(request: Request, call_next):
    """共有トークンで状態変更・映像系エンドポイントを保護する。

    - CAMERA_API_TOKEN 未設定なら素通し（fail-open・キオスク保護のブリック防止）
    - localhost（キオスク）と /health・/status、CORS preflight(OPTIONS) は免除
    - それ以外は X-Camera-Token ヘッダ、または ?token= クエリを定数時間比較で検証
      （リモートの通常経路は Caddy が /camera/* でヘッダ注入するのでクエリ不要。
      ?token= は Caddy を経由しない LAN 直アクセス（例: pi-camera.local:8001。
      <img> はヘッダを付けられない）のためのフォールバック。クエリはアクセス
      ログに残るため常用しない）
    """
    if CAMERA_API_TOKEN and request.method != "OPTIONS":
        path = request.url.path
        client_host = request.client.host if request.client else ""
        if path not in AUTH_EXEMPT_PATHS and client_host not in AUTH_EXEMPT_HOSTS:
            provided = request.headers.get(
                "X-Camera-Token"
            ) or request.query_params.get("token", "")
            # bytes 比較にする（非 ASCII の str を compare_digest に渡すと
            # TypeError で 500 になるため。定数時間比較は維持）
            if not secrets.compare_digest(
                provided.encode("utf-8"), CAMERA_API_TOKEN.encode("utf-8")
            ):
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


# Add CORS middleware to allow frontend access.
# 具体的オリジンのみ許可し、credentials は使わない（トークンはヘッダ/クエリで渡す）。
# - localhost（開発・キオスク直アクセス）
# - pi-camera.local（Caddy 非経由の LAN 直アクセス。urls.ts の同名分岐に対応）
# - Tailscale CGNAT 100.64.0.0/10（キオスクのページ配信元 http://100.64.0.10:3000 等）
# - coordinate.unicco.app（Cloudflare 経由・実際は同一オリジンだが明示）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://coordinate.unicco.app"],
    allow_origin_regex=(
        r"^https?://(localhost|127\.0\.0\.1|pi-camera\.local|"
        r"100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])"
        r"(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){2})(:\d+)?$"
    ),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

camera_service = CameraService()


@app.post("/capture")
async def capture(force: bool = False):
    try:
        # capture_photo はブロッキング（camera_lock + time.sleep + I/O）のため
        # スレッドプールで実行して event loop をブロックしない
        filename = await asyncio.to_thread(
            camera_service.capture_photo,
            force_capture=force,
            trigger_source="touchscreen_api",
        )
        if filename:
            # 🖼️ プレビュー画像パス問題対策: photo_id を返す
            return {
                "status": "success",
                "filename": filename,
                "photo_id": filename,  # フロントエンドがプレビュー取得に使用
            }
        else:
            return {"status": "failed", "message": "Photo capture failed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/shutdown")
async def shutdown_pi():
    """撮影＋アップロード成功後などに Pi をグレースフルシャットダウン（halt）する。

    AUTO_SHUTDOWN_ENABLED=true のときのみ実行。無効時は何もせず disabled を返す。
    HA 側は ping 不応答を確認してからプラグを切る（halt 完了後に de-power）。
    """
    started = camera_service._perform_shutdown(reason="api request")
    if started:
        return {"status": "shutting_down"}
    return {
        "status": "disabled",
        "message": "AUTO_SHUTDOWN_ENABLED is not true",
    }


@app.post("/upload/{photo_id}")
async def upload_photo(photo_id: str):
    """指定された写真をバックエンドにアップロード."""
    try:
        # セキュリティ: ファイル名のサニタイゼーション
        import re

        if not re.match(r"^[a-zA-Z0-9_]+\.(jpg|jpeg|png)$", photo_id):
            raise HTTPException(status_code=400, detail="Invalid photo ID format")

        photo_path = os.path.join(camera_service.photos_dir, photo_id)

        # ファイル存在確認
        if not os.path.exists(photo_path):
            raise HTTPException(status_code=404, detail=f"Photo not found: {photo_id}")

        # ファイルがディレクトリ外を指していないかチェック
        if not os.path.abspath(photo_path).startswith(
            os.path.abspath(camera_service.photos_dir)
        ):
            raise HTTPException(status_code=403, detail="Access denied")

        # 再送ループと同じ経路を通す。存在確認と送信を別々にすると、両方が
        # 「まだ届いていない」と判断して同じ写真を 2 回上げる
        result = camera_service.upload_if_missing(photo_id)

        if result == "already":
            return {
                "status": "success",
                "message": f"Photo {photo_id} is already on the backend",
            }
        if result == "sent":
            camera_service.logger.info(f"Manual upload successful: {photo_id}")
            return {
                "status": "success",
                "message": f"Photo {photo_id} uploaded successfully",
            }
        if result == "unknown":
            # 届いているか確認できていない。送ると重複しうるので送っていない
            raise HTTPException(
                status_code=503, detail="Backend unreachable; not uploaded"
            )
        if result == "missing_file":
            raise HTTPException(status_code=404, detail=f"Photo not found: {photo_id}")
        raise HTTPException(status_code=500, detail="Upload failed")

    except HTTPException:
        raise
    except Exception as e:
        camera_service.logger.error(f"Error in manual upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/photo/{photo_id}/discard")
async def discard_photo(photo_id: str):
    """撮り直しで捨てた写真を再送の対象から外す.

    印が無くても 200 を返す。UI は撮り直しのたびに投げるので、既に送り終えた写真や
    2 回目の撮り直しに対しても叩かれる。
    """
    if not re.match(r"^[a-zA-Z0-9_]+\.(jpg|jpeg|png)$", photo_id):
        raise HTTPException(status_code=400, detail="Invalid photo ID format")

    was_marked = camera_service.discard_unsent(photo_id)
    return {"status": "discarded", "was_marked": was_marked}


@app.get("/photo/{photo_id}")
async def get_photo(photo_id: str):
    """🖼️ プレビュー画像配信エンドポイント - Issue #162 対策."""
    try:
        # セキュリティ: ファイル名のサニタイゼーション
        import re

        if not re.match(r"^[a-zA-Z0-9_]+\.(jpg|jpeg|png)$", photo_id):
            raise HTTPException(status_code=400, detail="Invalid photo ID format")

        photo_path = os.path.join(camera_service.photos_dir, photo_id)

        # ファイル存在確認
        if not os.path.exists(photo_path):
            raise HTTPException(status_code=404, detail=f"Photo not found: {photo_id}")

        # ファイルがディレクトリ外を指していないかチェック
        if not os.path.abspath(photo_path).startswith(
            os.path.abspath(camera_service.photos_dir)
        ):
            raise HTTPException(status_code=403, detail="Access denied")

        # 画像ファイルを返す
        return FileResponse(photo_path, media_type="image/jpeg", filename=photo_id)

    except HTTPException:
        raise
    except Exception as e:
        camera_service.logger.error(f"Error serving photo {photo_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve photo") from e


@app.get("/photos/{photo_id}")
async def get_photo_alt(photo_id: str):
    """🖼️ 代替パス /photos/{photo_id} - UI の複数エンドポイント試行に対応."""
    return await get_photo(photo_id)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "auth_enforced": bool(CAMERA_API_TOKEN),
        "camera_mode": camera_service.camera_mode,
        "thermal_status": {
            "cpu_temperature": camera_service.cpu_temperature,
            "throttle_level": camera_service.thermal_throttle_level,
            "throttle_level_name": ["正常動作", "軽度制御", "重度制御"][
                camera_service.thermal_throttle_level
            ],
        },
        "pir_status": {
            "enabled": camera_service.pir_enabled,
            "simulation_mode": camera_service.pir_simulation_mode,
            "detections_count": len(camera_service.pir_detections),
            "daily_photo_taken": camera_service.daily_photo_taken,
        },
        "display_status": {
            "backlight_device": camera_service.backlight_device,
            "backlight_available": camera_service.backlight_device is not None,
        },
        "system_info": {
            "uptime": (
                time.time() - camera_service.start_time
                if hasattr(camera_service, "start_time")
                else 0
            ),
            "platform": platform.system(),
        },
    }


@app.get("/status")
async def status():
    """Camera service status - simplified version of /health."""
    detection = camera_service.detection_resolution
    capture = camera_service.capture_resolution
    degrees = fine_rotation_deg()
    requested_zoom = center_zoom()
    return {
        "service": "coordinate-camera",
        "status": "running",
        "camera_mode": camera_service.camera_mode,
        "pir_enabled": camera_service.pir_enabled,
        "thermal_throttle_level": camera_service.thermal_throttle_level,
        "display_state": camera_service.display_state,
        "pir_inactivity_timeout": camera_service.display_timeout,
        # API に届いていない写真の件数。0 でなければその日の記録が欠けている
        "unsent_photos": len(camera_service.list_unsent()),
        # 画角が食い違っていないかの判定材料。設定ファイルは git の外に
        # あるので、実機の値はここでしか確かめられない。
        # 🚨 **`sensor_mode` が null なら固定できていない**＝待機用と撮影用が別のモードに
        # 落ちて画角が変わりうる（IMX708 の 1536×864 は中央 2/3 しか読まない）。
        # ⚠️ `aspect_matches` は別口の罠（比が違うと画面側の切り落とし量まで変わる）。
        # **完全一致では見ない**。捕まえたいのは 4:3 と 16:9 の取り違えで、1366×768 の
        # ような端数の解像度を不一致にすると誤検知しかしなくなる
        "resolution": {
            "detection": f"{detection[0]}x{detection[1]}",
            "capture": f"{capture[0]}x{capture[1]}",
            "sensor_mode": (
                f"{camera_service.sensor_mode[0]}x{camera_service.sensor_mode[1]}"
                if camera_service.sensor_mode
                else None
            ),
            "aspect_matches": math.isclose(
                detection[0] / detection[1], capture[0] / capture[1], rel_tol=0.01
            ),
        },
        # 傾き補正と中央切り出し。⚠️ **`zoom` のぶんだけ写る範囲が狭くなる**。
        # `center_zoom` が回転に必要な拡大以上なら、傾き補正はタダで乗っている
        "orientation": {
            "quarter_turn": os.environ.get("CAMERA_STREAM_ROTATION", "0"),
            "fine_degrees": degrees,
            "center_zoom": requested_zoom,
            "zoom": round(effective_zoom(capture, degrees, requested_zoom), 4),
        },
    }


@app.get("/capture/preview")
async def capture_preview():
    """Get a single frame for live preview without saving."""
    from fastapi.responses import Response

    try:
        frame = None

        if camera_service.picamera2:
            # Hardware camera mode using Picamera2
            with camera_service.camera_sync_lock:
                array = camera_service.picamera2.capture_array("main")
            # Convert BGR to RGB if needed
            if len(array.shape) == 3 and array.shape[2] == 3:
                frame = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
            else:
                frame = array
        else:
            # Generate error frame if no camera
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                frame,
                "No Camera Available",
                (150, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
                2,
            )

        if frame is not None:
            frame = orient_frame(frame)

            # Encode frame as JPEG
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

            return Response(
                content=jpeg.tobytes(),
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        else:
            # Generate error frame
            error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                error_frame,
                "Camera Error",
                (200, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 0, 255),
                2,
            )
            _, jpeg = cv2.imencode(".jpg", error_frame)
            return Response(content=jpeg.tobytes(), media_type="image/jpeg")

    except Exception as e:
        camera_service.logger.error(f"Error capturing preview frame: {e}")
        # Generate error frame
        error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(
            error_frame,
            "Preview Error",
            (180, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            2,
        )
        _, jpeg = cv2.imencode(".jpg", error_frame)
        return Response(content=jpeg.tobytes(), media_type="image/jpeg")


# PIR Sensor simulation endpoints for testing
@app.post("/pir/simulate")
async def simulate_pir_motion():
    """PIRセンサーのモーション検知をシミュレート（テスト用）."""
    if not camera_service.pir_enabled:
        raise HTTPException(status_code=400, detail="PIR sensor not enabled")

    if not camera_service.pir_simulation_mode:
        raise HTTPException(status_code=400, detail="PIR simulation mode not enabled")

    # PIRモーション検知をシミュレート
    camera_service._on_pir_motion()

    return {
        "status": "success",
        "message": "PIR motion simulated",
        "timestamp": time.time(),
        "current_mode": camera_service.current_mode,
        "detections_count": len(camera_service.pir_detections),
    }


@app.get("/pir/status")
async def get_pir_status():
    """PIRセンサーの現在の状態を取得."""
    return {
        "enabled": camera_service.pir_enabled,
        "simulation_mode": camera_service.pir_simulation_mode,
        "daily_photo_taken": camera_service.daily_photo_taken,
        "last_photo_date": (
            str(camera_service.last_photo_date)
            if camera_service.last_photo_date
            else None
        ),
        "detections_count": len(camera_service.pir_detections),
        "detection_threshold": camera_service.pir_detection_threshold,
        "detection_window": camera_service.pir_detection_window,
        "timestamp": time.time(),
    }


@app.post("/pir/reset")
async def reset_pir_daily_status():
    """PIRセンサーの1日1回撮影状態をリセット（テスト用）."""
    camera_service.daily_photo_taken = False
    camera_service.last_photo_date = None
    camera_service.pir_detections.clear()

    return {
        "status": "success",
        "message": "PIR daily status reset",
        "timestamp": time.time(),
    }


@app.post("/display/off")
async def turn_off_display():
    """撮影完了後やタイムアウト時にディスプレイを完全オフにする."""
    try:
        camera_service.logger.info(
            "Display turn off requested via /display/off endpoint"
        )

        # 既存のタイマーをキャンセル
        if camera_service.display_off_timer:
            camera_service.display_off_timer.cancel()
            camera_service.display_off_timer = None

        # ディスプレイオフ処理を実行
        success = camera_service.turn_off_display()

        if success:
            return {
                "status": "success",
                "message": "Display turned off successfully",
                "timestamp": time.time(),
            }
        else:
            return {
                "status": "partial_success",
                "message": "Display turn off partially completed with some warnings",
                "timestamp": time.time(),
            }

    except Exception as e:
        camera_service.logger.error(f"Error in /display/off endpoint: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to turn off display: {str(e)}"
        )


@app.post("/display/on")
async def turn_on_display():
    """タッチ操作などでディスプレイを点灯させる（PIR 以外の復帰経路）.

    バックライトは通常 PIR モーションでしか点灯しないため、タッチUI から
    この endpoint を叩くことで「画面に触れれば点く」を実現する。turn_on_display()
    が点灯と消灯タイマーの再アームを両方処理する。
    """
    try:
        camera_service.logger.info("Display turn on requested via /display/on endpoint")

        # 点灯処理（内部で消灯タイマーを再アームする）
        success = camera_service.turn_on_display()

        if success:
            return {
                "status": "success",
                "message": "Display turned on successfully",
                "timestamp": time.time(),
            }
        else:
            return {
                "status": "partial_success",
                "message": "Display turn on partially completed with some warnings",
                "timestamp": time.time(),
            }

    except Exception as e:
        camera_service.logger.error(f"Error in /display/on endpoint: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to turn on display: {str(e)}"
        )


@app.post("/camera/restart")
async def restart_camera():
    """Manual Picamera2 restart endpoint for touchscreen troubleshooting."""
    try:
        result = camera_service.restart_camera_subsystem()
        result["timestamp"] = time.time()
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        camera_service.logger.error(f"Error in /camera/restart endpoint: {e}")
        raise HTTPException(
            status_code=500, detail="Unexpected error while restarting camera"
        ) from e


_active_stream_event: asyncio.Event | None = None


@app.get("/stream")
async def stream():
    """Generate camera stream frames for live preview."""
    global _active_stream_event
    from fastapi.responses import StreamingResponse

    # Last-writer-wins: 既存のストリーム接続があれば終了させる
    if _active_stream_event is not None:
        _active_stream_event.set()
    cancel_event = asyncio.Event()
    _active_stream_event = cancel_event

    async def generate():
        global _active_stream_event
        last_good_frame = None
        try:
            while not cancel_event.is_set():
                try:
                    frame = None

                    if camera_service.picamera2:
                        # Hardware camera mode using Picamera2
                        # capture_array はブロッキング呼び出しのため、スレッドプールで実行して
                        # event loop をブロックしない（撮影リクエスト等の並行処理を可能にする）
                        try:
                            array = await asyncio.to_thread(
                                camera_service.picamera2.capture_array, "main"
                            )
                            if len(array.shape) == 3 and array.shape[2] == 3:
                                frame = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
                            else:
                                frame = array
                        except Exception as picam_error:
                            # 1回リトライ
                            try:
                                array = await asyncio.to_thread(
                                    camera_service.picamera2.capture_array, "main"
                                )
                                if len(array.shape) == 3 and array.shape[2] == 3:
                                    frame = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
                                else:
                                    frame = array
                            except Exception:
                                camera_service.logger.error(
                                    f"Picamera2 capture_array failed (after retry): {picam_error}"
                                )
                                if last_good_frame is not None:
                                    frame = last_good_frame
                                else:
                                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                                    cv2.putText(
                                        frame,
                                        "Camera Error",
                                        (200, 240),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        1,
                                        (0, 0, 255),
                                        2,
                                    )
                    elif camera_service.camera_mode == "simulation":
                        # Generate simulation frame
                        current_time = time.time()
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)

                        color_shift = int((current_time * 50) % 255)
                        frame[:, :] = [color_shift, (255 - color_shift) // 2, 100]

                        from datetime import datetime

                        timestamp_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cv2.putText(
                            frame,
                            "SIMULATION STREAM",
                            (120, 200),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.2,
                            (255, 255, 255),
                            3,
                        )
                        cv2.putText(
                            frame,
                            timestamp_text,
                            (180, 250),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (255, 255, 255),
                            2,
                        )
                        cv2.putText(
                            frame,
                            "Camera Mode: Simulation",
                            (150, 300),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 0),
                            2,
                        )
                    else:
                        camera_service.logger.warning("No camera available")
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)
                        cv2.putText(
                            frame,
                            "No Camera Available",
                            (150, 240),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,
                            (0, 0, 255),
                            2,
                        )

                    if frame is not None:
                        # カメラから取得した正常フレームのみ保持（エラーフレームは除外）
                        if camera_service.picamera2 and frame is not last_good_frame:
                            last_good_frame = frame

                        frame = orient_frame(frame)

                        _, jpeg = cv2.imencode(".jpg", frame)

                        data = (
                            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                            + jpeg.tobytes()
                            + b"\r\n"
                        )
                        yield data

                        # 明示的にコンテキストスイッチを強制（localhost バッファリング対策）
                        await asyncio.sleep(0)

                    # 🔥 発熱対策: ストリーミングFPS削減 (GPU/CPU負荷 -33%)
                    # デフォルト10FPS (15FPS → 10FPS)
                    streaming_fps = float(os.environ.get("STREAMING_FPS", "10.0"))
                    frame_interval = 1.0 / streaming_fps
                    await asyncio.sleep(frame_interval)

                except Exception as e:
                    camera_service.logger.error(f"Error in stream generation: {e}")
                    camera_service.logger.error(
                        f"Camera mode: {camera_service.camera_mode}"
                    )
                    camera_service.logger.error(
                        f"Picamera2 available: {camera_service.picamera2 is not None}"
                    )

                    # last_good_frame があれば再送、なければエラーフレーム。
                    # ⚠️ 控えてあるのは向きを直す前のフレームなので、ここでも通す。
                    # 素通しすると再送のあいだだけ画が倒れる
                    if last_good_frame is not None:
                        _, jpeg = cv2.imencode(".jpg", orient_frame(last_good_frame))
                        yield (
                            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                            + jpeg.tobytes()
                            + b"\r\n"
                        )
                    else:
                        error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                        error_msg = f"Camera Error: {str(e)[:30]}"
                        cv2.putText(
                            error_frame,
                            error_msg,
                            (50, 240),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (0, 0, 255),
                            2,
                        )
                        _, jpeg = cv2.imencode(".jpg", error_frame)
                        yield (
                            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                            + jpeg.tobytes()
                            + b"\r\n"
                        )
                    await asyncio.sleep(1)
        finally:
            # 接続終了時にクリーンアップ
            if _active_stream_event is cancel_event:
                _active_stream_event = None

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",  # Keep-Alive を無効化してバッファリング問題を回避
        },
    )


def run_api():
    # Get port from environment variable or default to 8001
    port = int(os.environ.get("CAMERA_PORT", "8001"))
    print(f"Camera service starting on port: {port}")

    # LAN と Cloudflare Tunnel（camera.unicco.app）から到達させる意図的な公開。
    # 保護は共有トークン + localhost 免除で、設計は deploy/docs/camera-service-auth.md
    uvicorn.run(
        app,
        host="0.0.0.0",  # noqa: S104
        port=port,
        # localhost アクセス時のバッファリング問題対策
        server_header=False,
        access_log=False,
        loop="asyncio",  # デフォルトの asyncio ループを明示的に指定
        # ワーカー設定
        workers=1,
        # インターフェース設定
        interface="asgi3",
        # タイムアウト設定
        timeout_keep_alive=5,
    )


def shutdown_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    import signal

    signal_names = {signal.SIGINT: "SIGINT", signal.SIGTERM: "SIGTERM"}
    signal_name = signal_names.get(signum, f"Signal {signum}")
    camera_service.logger.info(
        f"Received {signal_name}, initiating graceful shutdown..."
    )

    try:
        camera_service.cleanup_resources()
    except Exception as e:
        camera_service.logger.error(f"Error during shutdown cleanup: {e}")

    camera_service.logger.info("Camera service shutdown completed")
    exit(0)


if __name__ == "__main__":
    import signal

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    camera_service.logger.info("Signal handlers registered for graceful shutdown")

    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()

    # Initialize display after API startup
    def init_display_after_startup():
        time.sleep(3)  # Wait for API to be ready
        camera_service.logger.info("Initializing display state after API startup...")
        # turn_on_display()がstate設定とタイマー開始を適切に処理する
        success = camera_service.turn_on_display()
        if success:
            camera_service.logger.info("✅ Display initialized successfully")
        else:
            camera_service.logger.warning("⚠️ Failed to initialize display")

    threading.Thread(target=init_display_after_startup, daemon=True).start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # This will trigger SIGINT handler
        pass
