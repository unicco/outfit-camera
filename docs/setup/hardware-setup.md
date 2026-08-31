# ハードウェアセットアップガイド

Raspberry Pi でのカメラシステム構築とタッチスクリーン設定のための包括的ガイドです。

## 🎯 セットアップ目標

- Sony IMX500 AI カメラの設定
- タッチスクリーン全画面表示の実現
- PIR センサーとの連動
- WebSocket 通信によるリアルタイム更新

## 🔧 必要なハードウェア

### 必須コンポーネント

- **Raspberry Pi 5** (8GB RAM 推奨)
- **Sony IMX500 AI カメラ** (MIPI CSI-2 接続)
- **タッチスクリーン** (7インチ以上推奨)
- **PIR センサー** (人感検知用)
- **MicroSD カード** 64GB+ (Class 10 以上)
- **電源アダプタ** 公式 Raspberry Pi 5 アダプタ (5V 5A)

### 推奨コンポーネント

- **冷却システム** パッシブヒートシンクまたはアクティブ冷却
- **保護ケース**
- **Ethernet ケーブル** (安定したネットワーク接続用)

## 📷 カメラセットアップ

### 1. 物理的な接続

#### カメラモジュール接続

1. Raspberry Pi の電源を切る
2. CSI-2 コネクタにカメラモジュールを接続
3. ケーブルの向きを確認（青い部分が USB ポート側）
4. コネクタをしっかりと固定

#### 接続確認

```bash
# カメラハードウェア検出
libcamera-hello --list-cameras

# 期待される出力例:
# Available cameras:
# 0 : imx500 [4096x3072] (/base/soc/i2c0mux/i2c@1/imx500@1a)
```

### 2. ソフトウェア設定

#### システムパッケージインストール

```bash
# 必須パッケージをインストール
sudo apt update
sudo apt install -y \
    python3-opencv \
    python3-numpy \
    python3-libcamera \
    python3-picamera2 \
    python3-pillow \
    libcamera-apps \
    libcamera-dev
```

#### カメラ有効化

```bash
# raspi-config でカメラを有効化
sudo raspi-config
# Advanced Options > Camera Interface > Enable を選択
```

#### 環境変数設定

```bash
# .env ファイルに追加
cat >> .env << EOF
# カメラモード（必須）
CAMERA_MODE=hardware

# 撮影画像の送信先。API は VPS で動くので Tailscale IP を指す
# （API_URL は後方互換のフォールバックなので新規に書かない）
BACKEND_API_URL=http://<VPS の Tailscale IP>:8000

# 写真保存ディレクトリ
PHOTOS_DIR=/home/pi/coordinate-recorder/photos
EOF
```

### 3. カメラ動作テスト

#### 基本動作確認

```bash
# カメラ撮影テスト
libcamera-jpeg -o test.jpg

# カメラストリーミングテスト（5秒間）
libcamera-hello --timeout 5000
```

#### サービス動作確認

```bash
# カメラサービス起動
sudo systemctl start coordinate-camera

# ストリーミング確認
curl -I http://localhost:8001/stream
```

## 📺 タッチスクリーンセットアップ

### 1. ハードウェア接続

#### ディスプレイ接続

- HDMI または DSI 接続でディスプレイを接続
- タッチパネル用 USB ケーブルを接続
- 必要に応じて電源を接続

### 2. ディスプレイ設定

#### 解像度設定

```bash
# /boot/config.txt を編集
sudo nano /boot/config.txt

# 以下を追加/変更
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=87
hdmi_cvt 1024 600 60 6 0 0 0
display_rotate=0
```

#### タッチ機能設定

```bash
# タッチデバイス確認
ls /dev/input/event*

# タッチ機能テスト
sudo apt install evtest
sudo evtest /dev/input/event0  # タッチデバイス
```

### 3. 全画面表示設定

#### Chromium Kiosk モード

```bash
# 自動起動スクリプト作成
cat > ~/autostart.sh << 'EOF'
#!/bin/bash
sleep 10

# 全画面ブラウザ起動
chromium-browser \
  --kiosk \
  --no-sandbox \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --autoplay-policy=no-user-gesture-required \
  http://localhost:3000/touchscreen
EOF

chmod +x ~/autostart.sh
```

#### systemd 自動起動設定

unit を手書きせず、リポジトリの `systemd/coordinate-kiosk.service` を `deploy/setup-pi.sh` に入れさせる。`graphical.target` が使えるときだけ `coordinate-kiosk.service` と `kiosk-health-monitor.service` が起動する。

```bash
cd ~/coordinate-recorder
bash deploy/setup-pi.sh

sudo systemctl status coordinate-kiosk
```

管理スクリプトの使い方は [kiosk-scripts-guide.md](./kiosk-scripts-guide.md) を参照。

## 🔍 PIR センサーセットアップ

### 1. ハードウェア接続

#### GPIO 接続

```
PIR センサー -> Raspberry Pi
VCC         -> 5V (Pin 2)
GND         -> GND (Pin 6)
OUT         -> GPIO 18 (Pin 12)
```

### 2. センサー設定

#### 環境変数設定

```bash
# .env ファイルに追加
cat >> .env << EOF
# PIR センサー設定
PIR_SENSOR_PIN=18
PIR_SENSITIVITY_THRESHOLD=0.7
PIR_DETECTION_COOLDOWN=30
EOF
```

#### 動作テスト

```bash
# GPIO 動作確認
python3 -c "
import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.IN)

print('PIR Sensor Test - Move in front of sensor')
for i in range(20):
    if GPIO.input(18):
        print(f'Motion detected! ({i})')
    else:
        print(f'No motion ({i})')
    time.sleep(1)

GPIO.cleanup()
"
```

## 🌐 ネットワーク設定

### Wi-Fi 設定（オプション）

```bash
# Wi-Fi 設定
sudo raspi-config
# Network Options > Wi-Fi > SSID とパスワードを入力
```

### 固定 IP 設定（推奨）

```bash
# /etc/dhcpcd.conf を編集
sudo nano /etc/dhcpcd.conf

# 以下を追加
interface eth0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

## 🔧 システム最適化

### パフォーマンス設定

```bash
# GPU メモリ分割調整
sudo raspi-config
# Advanced Options > Memory Split > 256 を選択

# swap 設定調整
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# CONF_SWAPSIZE=2048 に変更
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### 自動起動設定

`deploy/setup-pi.sh` が `systemd/` の unit を配置して enable する。個別に `systemctl enable` しない。

```bash
cd ~/coordinate-recorder
bash deploy/setup-pi.sh
```

Pi に入るのはカメラと Kiosk だけ（`coordinate-camera` / `coordinate-kiosk` / `kiosk-health-monitor` / `camera-pir-monitor`）。API・UI・DB は VPS 側なので、Pi で `coordinate-api` や `coordinate-ui` を有効化しない。1 台構成時代の遺物は setup-pi.sh が停止・削除する。

## 🔍 診断・トラブルシューティング

### 診断スクリプト実行

```bash
# 総合診断実行
./scripts/debug/diagnose-camera-issue.sh

# ハードウェア状態確認
./scripts/debug/hardware-check.sh
```

### よくある問題

#### カメラが認識されない

1. 物理接続を確認
2. `sudo reboot` でシステム再起動
3. `libcamera-hello --list-cameras` で再確認

#### タッチが反応しない

1. USB 接続を確認
2. `ls /dev/input/event*` でデバイス存在確認
3. ドライバーの再インストール

#### パフォーマンスが低い

1. 冷却システムの確認
2. 電源アダプターの確認
3. メモリ使用量の最適化

## 📚 次のステップ

ハードウェアセットアップが完了したら：

1. [システムセットアップ](./system-setup.md) に進む
2. [アクセス設定](./access-setup.md) を実施
3. 運用デプロイ を確認
