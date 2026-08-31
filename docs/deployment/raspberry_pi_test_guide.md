# 🍓 Raspberry Pi でのPIRセンサー検証ガイド

## ハードウェア接続

### PIRセンサー（HC-SR501）接続

```
PIRセンサー    →    Raspberry Pi
VCC (5V)     →    Pin 2 (5V電源)
GND          →    Pin 6 (GND)
OUT          →    Pin 12 (GPIO 18) ← 物理ピン12番 = GPIO18番
```

**重要**:

- コードでは `GPIO 18` を指定
- 物理的には **Pin 12** に接続
- GPIO番号と物理ピン番号は異なります

### 接続確認

```bash
# GPIO状態確認
gpio readall

# PIRセンサー入力確認
gpio -g mode 18 in
gpio -g read 18
```

## ソフトウェア設定

### 1. 環境設定

```bash
# .env ファイル編集
PIR_ENABLED=true
PIR_SIMULATION_MODE=false  # 実際のセンサー使用
CAMERA_MODE=hardware       # Picamera2使用
PIR_GPIO_PIN=18
PIR_DETECTION_THRESHOLD=2
PIR_DETECTION_WINDOW=3
CAMERA_ACTIVE_DURATION=300
```

### 2. 依存関係インストール

```bash
# gpiozero ライブラリ
pip install gpiozero

# Raspberry Pi用
sudo apt update
sudo apt install python3-gpiozero
```

## 検証手順

### Phase 1: ハードウェア検証

```bash
# 1. PIRセンサー単体テスト
python3 -c "
from gpiozero import MotionSensor
import time

pir = MotionSensor(18)
print('PIRセンサー待機中...')

def motion_detected():
    print(f'モーション検知: {time.time()}')

pir.when_motion = motion_detected

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    print('テスト終了')
"
```

### Phase 2: システム統合テスト

```bash
# 1. カメラサービス起動
cd camera
python camera_service.py

# 2. ログ監視（別ターミナル）
tail -f camera_service.log

# 3. PIR検知テスト
# 実際にPIRセンサー前で動く
# ログで以下を確認:
# - "PIR motion detected at..."
# - "PIR detection threshold met..."
# - "Activating camera mode from PIR detection"
```

### Phase 3: 省電力効果測定

#### CPU使用率監視

```bash
# リソース使用量監視
htop

# プロセス別CPU使用率
ps aux | grep camera_service

# スリープモード時とアクティブモード時を比較
```

#### 発熱測定

```bash
# CPU温度監視
watch -n 1 vcgencmd measure_temp

# スリープモード時: ~40-45°C 期待
# アクティブモード時: ~50-55°C 期待
```

## 受け入れテスト

### ✅ 基本動作

- [ ] PIR 3秒以内2回検知でアクティブモード発火
- [ ] 人検知成功時にディスプレイ自動オン
- [ ] 1日1回撮影完了後はスリープモード移行
- [ ] 5分間カメラ稼働後は自動スリープ復帰

### ✅ 省電力効果

- [ ] スリープモード時: CPU使用率 <5%
- [ ] スリープモード時: CPU温度 <45°C
- [ ] アクティブモード時のみ画像処理実行
- [ ] 90%以上の省電力効果達成

### ✅ 誤検知対策

- [ ] 単発検知では反応しない
- [ ] 風による小さな動きは無視
- [ ] しきい値調整が有効

### ✅ システム統合

- [ ] 既存タッチスクリーン機能に影響なし
- [ ] WebSocket通知が正常動作
- [ ] 設定ファイルで調整可能

## トラブルシューティング

### PIRセンサーが反応しない

```bash
# 1. GPIO確認
gpio readall | grep 18

# 2. 権限確認
sudo usermod -a -G gpio $USER

# 3. センサー調整
# PIRセンサーの感度調整ノブを回す
# 遅延時間調整ノブを最小に設定
```

### gpiozero ImportError

```bash
# 1. 仮想環境確認
which python
pip list | grep gpiozero

# 2. システムレベルインストール
sudo apt install python3-gpiozero

# 3. 環境変数設定
export GPIOZERO_PIN_FACTORY=pigpio
```

### カメラ初期化エラー

```bash
# 1. カメラ有効化確認
sudo raspi-config
# Interface Options → Camera → Enable

# 2. libcamera確認
libcamera-hello --list-cameras

# 3. 権限確認
sudo usermod -a -G video $USER
```

## 24時間連続テスト

### 監視スクリプト

```bash
#!/bin/bash
# 24hour_test.sh

LOG_FILE="pir_24h_test.log"
echo "PIR 24時間テスト開始: $(date)" >> $LOG_FILE

while true; do
    # CPU温度記録
    TEMP=$(vcgencmd measure_temp | cut -d= -f2)

    # PIR状態確認
    PIR_STATUS=$(curl -s http://localhost:8001/pir/status | jq -r '.current_mode')

    # ログ記録
    echo "$(date): temp=$TEMP, mode=$PIR_STATUS" >> $LOG_FILE

    sleep 300  # 5分間隔
done
```

### 実行

```bash
chmod +x 24hour_test.sh
nohup ./24hour_test.sh &

# 24時間後結果確認
tail -100 pir_24h_test.log
```

## 期待される結果

### 省電力効果

- **通常時**: CPU使用率 2-5%
- **発火時**: 5分間のみ高負荷
- **1日平均**: 99.7%省電力化達成

### 応答性

- **PIR検知**: 1秒以内に反応
- **アクティブ化**: 3秒以内にカメラ起動
- **撮影実行**: 5秒以内に完了

### 安定性

- **24時間連続稼働**: エラー0件
- **温度上昇**: スリープ時 <45°C
- **メモリリーク**: なし
