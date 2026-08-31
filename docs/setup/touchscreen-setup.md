# TouchScreen 全画面表示設定

Raspberry Pi でのタッチスクリーン全画面表示設定手順

## 🎯 目標

- TouchScreen UI を全画面表示 (`http://pi-camera.local:3000/touchscreen`)
- 実際のカメラフィード表示（シミュレーション画像ではなく）
- PIR センサー連動とWebSocket通信

## 📋 設定手順

### 1. 問題診断（推奨）

```bash
# Raspberry Pi で実行
cd /path/to/coordinate-recorder
./scripts/debug/diagnose-camera-issue.sh
```

### 2. カメラサービス起動

```bash
# 方法1: systemd サービスとして起動（推奨）
sudo systemctl start coordinate-camera

# 方法2: デバッグ用単独起動
./scripts/debug/start-simple-camera.sh

# 方法3: 強制再起動（既存プロセス全停止）
./scripts/debug/restart-camera-force.sh

# 方法4: すべて停止
./scripts/stop-development.sh
```

### 3. Kiosk モード設定

```bash
# TouchScreen 全画面表示設定（新しい統合システム）
# Kiosk サービスを配置する
cd ~/coordinate-recorder
bash deploy/setup-pi.sh
```

### 4. 再起動

```bash
sudo reboot
```

## 🔍 動作確認

### サービス状態確認

```bash
# SimpleCameraService ヘルスチェック
curl http://pi-camera.local:8001/health

# カメラ状態確認
curl http://pi-camera.local:8001/status

# TouchScreen UI 確認
curl http://pi-camera.local:3000/touchscreen
```

### WebSocket 接続確認

```bash
# ブラウザ開発者コンソールで確認
# ws://pi-camera.local:8001/ws への接続状況をチェック
```

## 🖥️ 表示内容

起動後の画面構成：

- **メイン画面**: TouchScreen UI (全画面)
- **カメラフィード**: 実際の Picamera2 映像 (1920x1080)
- **WebSocket**: リアルタイム PIR センサーイベント
- **PIR連動**: 人検出時の自動撮影

## 🐛 トラブルシューティング

### シミュレーション画像が表示される場合

1. SimpleCameraService が起動していない

   ```bash
   ps aux | grep camera_service_simple
   ```

2. 古い camera_service が動作中
   ```bash
   sudo pkill -f camera_service
   ./scripts/start-simple-camera.sh
   ```

### 全画面表示されない場合

1. Chromium の Kiosk モードが無効

   ```bash
   ps aux | grep chromium
   sudo pkill chromium
   chromium-browser --kiosk http://pi-camera.local:3000/touchscreen &
   ```

2. 自動起動設定の確認
   ```bash
   cat ~/.config/lxsession/LXDE-pi/autostart
   ```

### WebSocket 接続エラー

1. ポート 8001 での WebSocket エンドポイント確認
   ```bash
   curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
        -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: test" \
        http://pi-camera.local:8001/ws
   ```

## 📊 設定項目

### 環境変数（.env）

```bash
# Camera Service
CAMERA_PORT=8001
CAMERA_DETECTION_WIDTH=1920
CAMERA_DETECTION_HEIGHT=1080
CAMERA_CAPTURE_WIDTH=1920
CAMERA_CAPTURE_HEIGHT=1080
CAMERA_ROTATION_FINE_DEG=4.1
CAMERA_CENTER_ZOOM=1.5

# PIR Sensor
PIR_ENABLED=true
PIR_GPIO_PIN=18

# UI
VITE_API_URL=http://pi-camera.local:8000
VITE_CAMERA_URL=http://pi-camera.local:8001
```

### 解像度設定

- **Stream (表示用)**: 1920x1080 (待機・ライブ映像)
- **Capture (撮影用)**: 1920x1080 (保存する写真)

🚨 **解像度が変わると画角が変わる。**要求した大きさによって**選ばれるセンサーモードが変わり、
モードごとに読む範囲が違う**ため。IMX708 wide の実測（2026-08-26・`ScalerCrop`）:

| 要求 | 選ばれる raw モード | 読む範囲（4608×2592 中） | 画角 |
|---|---|---|---|
| 1920×1080 | 2304×1296 | (0, 0, 4608, 2592) | **全域** |
| 1280×720 | **1536×864** | (768, 432, **3072×1728**) | **中央 66.7%** |

⚠️ **`1536×864` だけが物理的に切り取った読み出し。**待機 1920×1080 / 撮影 1280×720 で
運用していた期間は、**保存写真だけがライブ映像の 2/3 の範囲**しか写っていなかった
（の「撮影時とプレビュー時の画角が違う」の正体）。

いまは `shared_sensor_mode` が**両方を賄えるモードを 1 つ選んで固定する**ので、片方だけ
解像度を下げても画角は動かない。

🚨 **その代わり、待機用だけ下げても発熱は減らない。**raw の読み出しは撮影用が要求する
モードに合わせて大きいまま固定されるため。**画角の一致と引き換えにした性質**なので、
発熱を抑えたいなら**両方下げる**（＝より小さいモードに落ちて**画角も狭くなる**）。
上の 2 つが同じ 1920×1080 である限りこのトレードオフは表に出ない（固定前と同じ
`2304×1296` が選ばれるだけ）。

⚠️ **固定できないと `/status` の `sensor_mode` が `null` になり、起動ログに警告が出る。**
その状態は画角が食い違う条件に戻っているので、解像度を見直すこと。

⚠️ **縦横比も揃える**（別口の罠）。画面（480×854 の縦パネル）は `object-cover` で嵌めるので、
比が違うと削られる量まで変わる。

```bash
# sensor_mode が入っていること・aspect_matches が true であること
curl -s http://pi-camera.local:8001/status | python3 -m json.tool
```

### 傾きの補正

カメラは箱に固定してあり、`CAMERA_STREAM_ROTATION=90` で 4 分の 1 回転を打ち消している。
それでも画が傾いて見えるときは `CAMERA_ROTATION_FINE_DEG` で起こす。

**実機の値は `+4.1`**（2026-08-26 深夜に測定）。単体だと拡大 1.125＝画角を 12.5% 失うが、
**下記の中央切り出しと併用すればタダで乗る**。

### 🚨 角度は「光軸上に垂らした下げ振り」で測る

**ドア枠や戸棚の縁から測ってはいけない。**カメラが下を向いているので**世界の垂直線は画像上で
収束**し、画面の左右で**符号が逆**になる。片側の線ばかり拾うと丸ごとバイアスが乗る
（実際にこの方法で `-1.4` と出したが、正しい値は `+4.1` で**符号も大きさも違った**）。
**光軸上では収束の寄与がゼロ**なので、そこに垂直基準を置けば仮定なしで読める。

1. 紐に重りを付けて（ねこじゃらしでもよい）**画面の左右のちょうど真ん中**に垂らす。
   揺れが止まってから 1 枚撮る（`curl -s http://127.0.0.1:8001/capture/preview -o plumb.jpg`）
2. 紐を**行ごとに追跡**して直線回帰する（Hough は背景の直線を拾うので細線追跡のほうが確実）
3. 候補の角度で回してから 2 を測り直し、**残差が 0 に最も近い値**を採る。
   符号を逆にすると倍にずれるので、**必ず両方向を試して悪化するほうを捨てる**
4. 可能なら**別の垂直物でも裏を取る**（実機では紐 −4.13 度 / 黄色い帯 −3.25 度 → `+4.1` で
   どちらも 0 付近に落ちた）

良い測定の目安: **残差 0.2px 前後・上中下の 1/3 で 0.1 度以内に一致**。残差が数 px なら
別の物を拾っている。

⚠️ **まず物理的に直せないかを試す。**シム 1 枚で直るなら計算も画角も要らない。

## 中央切り出し

`CAMERA_CENTER_ZOOM`（既定 `1.0`）で中央だけを使う。

- **広角レンズの歪みが小さい中心部に寄る**ので、顔の引き伸ばしが減る
- 遠めに立っても被写体が小さくならない
- ⭐ **傾き補正がタダになる。**回転は黒い角を出さないために拡大しているが、切り出しが
  その拡大以上なら上乗せが要らない（`effective_zoom`）。回転と切り出しは 1 つのアフィン
  変換にまとめてあるので、サンプリングも 1 回で済む
- ライブ映像・プレビュー・保存写真の**すべてに同じ切り出しが掛かる**ので、画角は一致したまま

**`1.5` にすると、以前の `1536×864` モード時代とちょうど同じ framing**になる。そこを起点に
実物合わせで決める。⚠️ 上限は `3.0`（それ以上は全身が入らない）。`1.0` 未満は縮小になるので
受け付けない。

実際に掛かっている拡大は `/status` の `orientation.zoom` で確認する。


## 🔄 システム構成

```
TouchScreen UI (port 3000)
    ↓ WebSocket
SimpleCameraService (port 8001)
    ↓ Picamera2
Raspberry Pi Camera (IMX500)
    ↓ PIR Trigger
PIR センサー (GPIO 17)
```
