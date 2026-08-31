# Picamera2 Setup and Troubleshooting

## 🎥 Overview

Picamera2 は Raspberry Pi の公式カメラライブラリで、IMX500 などの高性能カメラセンサーをサポートします。このドキュメントでは、仮想環境での Picamera2 設定と一般的な問題の解決方法を説明します。

## 🔧 Quick Setup

### 1. 自動セットアップ（推奨）

```bash
# Picamera2 対応仮想環境を自動作成
./scripts/setup/setup-picamera2-venv.sh

# または、依存関係のみインストール
./scripts/setup/install-camera-deps.sh
```

### 2. 手動セットアップ

```bash
# 1. システム依存関係のインストール
sudo apt update
sudo apt install -y python3-picamera2 libcamera-apps python3-opencv python3-numpy

# 2. 仮想環境作成（重要: --system-site-packages フラグ）
python3 -m venv --system-site-packages ~/coordinate-recorder-venv

# 3. 仮想環境アクティベート
source ~/coordinate-recorder-venv/bin/activate

# 4. 互換性のある依存関係をインストール
pip install 'numpy>=1.21,<2' 'opencv-python<4.12' pillow
pip install fastapi 'uvicorn[standard]' httpx python-multipart python-dotenv
```

## 🐛 Common Issues and Solutions

### Issue 1: `ModuleNotFoundError: No module named 'picamera2'`

**原因**: 仮想環境が system-site-packages にアクセスできない

**解決方法**:

```bash
# 既存の仮想環境を削除
rm -rf ~/coordinate-recorder-venv

# --system-site-packages フラグ付きで再作成
python3 -m venv --system-site-packages ~/coordinate-recorder-venv
```

### Issue 2: NumPy/OpenCV バージョン競合

**原因**: 新しい NumPy (2.x) と MediaPipe の非互換性

**解決方法**:

```bash
source ~/coordinate-recorder-venv/bin/activate
pip install 'numpy>=1.21,<2' 'opencv-python<4.12'
```

### Issue 3: カメラが USB モードで動作

**症状**: ログに "Falling back to USB camera" と表示

**解決方法**:

1. **仮想環境設定確認**:

   ```bash
   source ~/coordinate-recorder-venv/bin/activate
   python3 -c "import picamera2; print('Picamera2 available')"
   ```

2. **ハードウェア設定確認**:

   ```bash
   # カメラデバイス確認
   libcamera-hello --list-cameras

   # 設定ファイル確認
   grep -E "(camera|dtoverlay)" /boot/config.txt
   ```

3. **権限確認**:
   ```bash
   # video グループ追加
   sudo usermod -aG video $USER
   newgrp video
   ```

### Issue 4: システムサービスとの競合

**症状**: "Port 8001 is busy" エラー

**解決方法**:

```bash
# 古いシステムサービスを無効化
sudo systemctl stop coordinate-camera.service
sudo systemctl disable coordinate-camera.service

# start-development.sh を使用
./scripts/start-development.sh
```

## 📊 Verification Tests

### 1. 基本インポートテスト

```python
# 仮想環境で実行
import sys
print(f"Python: {sys.executable}")

import picamera2
from picamera2 import Picamera2
print("✅ Picamera2 imported successfully")

import cv2, numpy as np
print(f"✅ OpenCV: {cv2.__version__}, NumPy: {np.__version__}")
```

### 2. カメラハードウェアテスト

```python
from picamera2 import Picamera2

# カメラ情報取得
cameras = Picamera2.global_camera_info()
print(f"Found {len(cameras)} camera(s)")

for i, cam in enumerate(cameras):
    print(f"Camera {i}: {cam.get('Model')} at {cam.get('Id')}")

# カメラインスタンス作成テスト
picam2 = Picamera2()
print("✅ Camera instance created successfully")
picam2.close()
```

### 3. サービス動作テスト

```bash
# カメラサービス手動起動
cd coordinate-recorder
source ~/coordinate-recorder-venv/bin/activate
export PYTHONPATH="$PWD/src:$PYTHONPATH"
python camera/camera_service.py
```

## 🏗️ Architecture Details

### Virtual Environment Structure

```
~/coordinate-recorder-venv/
├── bin/python3              # Python interpreter
├── lib/python3.11/site-packages/  # Virtual env packages
└── pyvenv.cfg              # system-site-packages=true
```

### Package Resolution Order

1. Virtual environment packages (`~/coordinate-recorder-venv/lib/`)
2. **System packages** (`/usr/lib/python3/dist-packages/`) ← Picamera2 here
3. User packages (`~/.local/lib/`)

### Key Configuration

- **Virtual Environment**: `--system-site-packages` flag enables access to system Picamera2
- **NumPy Version**: `<2.0` for MediaPipe 互換性
- **OpenCV Version**: `<4.12` for NumPy 互換性
- **PYTHONPATH**: Includes `src/` for coordinate_recorder module

## 📝 Best Practices

### Development Workflow

1. **Use launch scripts**: Always use `./scripts/start-development.sh` instead of manual service startup
2. **Environment activation**: Use `source activate-picamera2-env.sh` for manual testing
3. **Dependency updates**: Re-run setup scripts after system updates

### Production Deployment

1. **System service conflicts**: Disable old systemd services before deploying
2. **Camera permissions**: Ensure web server user is in `video` group
3. **Hardware verification**: Test camera access after OS updates

### Debugging Commands

```bash
# Environment diagnosis
./scripts/debug/camera-startup-check.sh

# Hardware diagnosis
./scripts/debug/debug-camera.sh

# Service logs
tail -f logs/camera*service.log
```

## 🔗 References

- [Picamera2 Documentation](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf)
- [libcamera Documentation](https://libcamera.org/getting-started.html)
- [Raspberry Pi Camera Guide](https://www.raspberrypi.org/documentation/cameras/)

## 🆘 Getting Help

If issues persist after following this guide:

1. Run diagnostic scripts: `./scripts/debug/debug-camera.sh`
2. Check system logs: `sudo journalctl -u coordinate-camera.service`
3. Verify hardware: `libcamera-hello --list-cameras`
4. Test environment: `source activate-picamera2-env.sh && python -c "import picamera2"`
