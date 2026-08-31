# PIR センサーによるディスプレイ制御

このドキュメントでは、PIR（人感）センサーによるディスプレイの自動 ON/OFF 制御について説明します。

## 概要

PIR センサーの検知状態に基づいて、ディスプレイの電源（bl_power）を自動的に制御します。
輝度は一定のまま、省電力化のためにディスプレイの ON/OFF のみを行います。

## 動作仕様

### 基本動作

1. **PIR センサー検知時**

   - ディスプレイの電源を ON にします（`bl_power=0`）
   - 輝度は変更しません（既存の設定値を維持）
   - 15秒のタイマーを開始します

2. **15秒間操作がない場合**

   - ディスプレイの電源を OFF にします（`bl_power=1`）
   - 輝度は変更しません（既存の設定値を維持）

3. **タッチ操作時**
   - タイマーをリセットして15秒延長します
   - ディスプレイが OFF の場合は ON にします

### 技術仕様

- **制御対象**: `/sys/class/backlight/*/bl_power`

  - `0`: ディスプレイ ON
  - `1`: ディスプレイ OFF

- **制御スクリプト**: `scripts/display-power-helper.py`（優先）→ 無ければ `scripts/display-brightness.sh`
  - `power-on` / `power-off`: ディスプレイ電源のみ切り替え（明るさは触らない）

- **書き込み権限**: `sudo` は使わない。`bl_power` は `deploy/udev/99-coordinate-backlight.rules`、`brightness` は Raspberry Pi OS 標準の `60-backlight.rules` が `video` グループへ開放する。詳細は [Kiosk ディスプレイ制御](./kiosk-display-control.md)

## 環境変数

<!-- verify: camera/camera_service.py#PIR_ENABLED,PIR_GPIO_PIN,PIR_DETECTION_THRESHOLD,PIR_DETECTION_WINDOW,PIR_INACTIVITY_TIMEOUT 2026-08-10 -->

> ⚠️ **ここに書くのはコード上の既定値（`camera/camera_service.py`）であって、実機の運用値ではありません。**
> 実機の値は Pi の `~/coordinate-recorder/.env`（device-local・git 管理外）にあり、**既定値とは異なります**。
> 現在の値を知りたいときは Pi 上で `.env` を見てください。

```bash
# PIR センサー設定（カッコ内はコード上の既定値）
PIR_ENABLED=false               # PIR センサーの有効化。既定 false ← 実機は true で運用
PIR_GPIO_PIN=18                 # GPIO ピン番号
PIR_DETECTION_THRESHOLD=2       # 検知しきい値（回数）。既定 2
PIR_DETECTION_WINDOW=3          # 検知ウィンドウ（秒）。既定 3 ← ⚠️ 実機ではこの値だと点灯しない（下記）
PIR_INACTIVITY_TIMEOUT=30       # 無操作タイムアウト（秒）。既定 30
```

### 🚨 `PIR_DETECTION_WINDOW=3` は実機で機能しない

既定の「3 秒窓で 2 回検知」は、**実機の PIR が 6〜9 秒間隔でしか反応しないためほぼ絶対に満たされません**。
「近づいても点かない・時々点く」というムラの正体がこれです（2026-07-03 に特定）。

- 実機は `PIR_DETECTION_WINDOW=10`（検知間隔 6〜9 秒を包含）で解決。`THRESHOLD=1` は誤点灯で不安定なので不可
- より確実にするなら PIR モジュールのリトリガ・ジャンパを繰り返し（H）モードにする
- 🩺 **診断の罠**: `pinctrl get 18`（GPIO の瞬間読み）は**パルスの谷間を引くと LOW 張り付きに見え、
  センサー故障と誤判定します**。生存確認は
  `journalctl -u coordinate-camera --since '1 hour ago' | grep -c 'PIR motion detected'`（回数が出れば生存）で行ってください

## 実装詳細

### カメラサービス側

<!-- verify: camera/camera_service.py#display-power-helper.py,display-brightness.sh,_write_backlight,bl_power 2026-08-10 -->

1. **ディスプレイ ON 処理** (`turn_on_display()`)

   ```python
   # display-power-helper.py on（無ければ display-brightness.sh power-on）を実行
   # Chromium の再起動は行わない（kiosk サービスが管理）
   ```

2. **ディスプレイ OFF 処理** (`turn_off_display()`)

   ```python
   # display-power-helper.py off（無ければ display-brightness.sh power-off）を実行
   # どちらも無ければ _write_backlight() で sysfs を直接書く
   # Chromium の終了は行わない（起動したまま維持）
   ```

   スクリプトが見つからず sysfs にも書けない場合は `False` を返す。以前は失敗しても
   「成功」とログに出していた。

### UI 側

1. **PIR 検知のポーリング**

   - 500ms ごとに `/pir/status` エンドポイントをチェック
   - 検知があれば UI 側でもディスプレイタイマーをリセット

2. **タッチイベント処理**
   - タッチ操作時にディスプレイタイマーをリセット
   - `/touch` エンドポイントへの通知は削除（不要）

## トラブルシューティング

### ディスプレイが自動的に復帰する場合

以下のサービスが干渉している可能性があります：

```bash
# 確認
systemctl status display-always-on.service
systemctl status display-keepalive.service
systemctl status display-autofix.service
systemctl status display-no-timeout.service

# 無効化
sudo systemctl disable display-always-on.service
sudo systemctl disable display-keepalive.service
sudo systemctl disable display-autofix.service
sudo systemctl disable display-no-timeout.service
```

### PIR センサーが反応しない場合

<!-- verify: camera/camera_service.py#/pir/status,/pir/reset 2026-08-10 -->

1. GPIO ピンの確認

   ```bash
   gpio readall
   ```

2. PIR センサーの状態確認

   ```bash
   curl http://localhost:8001/pir/status
   ```

3. 日次撮影状態のリセット（テスト用）
   ```bash
   curl -X POST http://localhost:8001/pir/reset
   ```

### ディスプレイ制御のデバッグ

1. 現在の状態確認

   ```bash
   ./scripts/display-brightness.sh status
   ```

2. 手動制御テスト

   ```bash
   # 電源 ON（輝度そのまま）
   ./scripts/display-brightness.sh power-on

   # 電源 OFF（輝度そのまま）
   ./scripts/display-brightness.sh power-off
   ```

3. bl_power の監視
   ```bash
   watch -n 1 'cat /sys/class/backlight/*/bl_power'
   ```

## ディスプレイを制御するのは Pi だけ

**VPS（`coordinate-api.service`）からディスプレイを触らない。**バックライトは玄関の Pi にしか無く、
`camera_service.py` が PIR とタッチで所有している。VPS 側に制御を足しても
`/sys/class/backlight/` が空なので必ず失敗する。

かつて API の daily reset（毎朝 7:00）に `display-brightness.sh power-on` の呼び出しがあった
（coordinate-recorder#850・2025-09-06）。当時は API が Pi で動いていたので機能していたが、
**2026-03-11 に API が VPS 専用になった時点で成功しえなくなり**、以降 5.5 か月にわたって
毎朝 ERROR を 3 件出し続けた。実害はログが汚れることではなく、**daily reset 全体が常に
`success: False` になって、本当に壊れた日と区別がつかなくなること**だった
（で削除）。

朝ディスプレイが点かない事象が再発したら、**直す場所は Pi 側**（PIR の設定か
`camera_service` の点灯経路）であって VPS ではない。

## 関連ドキュメント

- [Kiosk ディスプレイ制御](./kiosk-display-control.md)
- [PIR センサー問題対応](../troubleshooting/pir-sensor-fixes.md)
- [トラブルシューティング](../troubleshooting/troubleshooting.md)
