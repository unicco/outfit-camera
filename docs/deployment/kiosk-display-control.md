# 🖥️ Kiosk ディスプレイ制御システム

PIR センサー連動の自動ディスプレイ制御と Chromium kiosk モードの統合システムです。

## 🔧 主な改善点

### 1. **バックライトデバイス自動検出**

- ハードコードされたパス (`/sys/class/backlight/10-0045`) を排除
- 複数のバックライトデバイスに対応
- Raspberry Pi 4/5 の両方で動作

### 2. **Chromium 統一制御**

- Firefox から Chromium に統一
- PIR センサー検知時の無縫な画面制御
- Ubuntu デスクトップを表示させない黒画面切り替え

### 3. **自動起動・復旧機能**

- systemd サービスによる自動起動
- 再起動後の自動復旧
- ヘルスチェック機能

### 4. **堅牢性向上**

- サービス間の依存関係管理
- タイムアウト・リトライ機能
- 詳細なログ記録

## 📁 関連ファイル

### 🔧 設定管理

- `.env` - 環境変数設定（`systemd/coordinate-camera.service` の `EnvironmentFile` で読み込まれ、unit の `Environment=` を上書きする）
- `config/brightness-control.conf` - ハードウェア固有設定

### 制御スクリプト

- `scripts/kiosk-display-manager.sh` - メイン kiosk 制御
- `scripts/display-brightness.sh` - バックライト制御（自動検出対応）
- `deploy/setup-pi.sh` - systemd サービスの配置・有効化（unit は手書きしない）
- `scripts/startup-health-check.sh` - 起動時ヘルスチェック

### サービス設定

- `systemd/coordinate-kiosk.service` - kiosk 自動起動サービス（systemd統合）
- `config/brightness-control.conf` - バックライト制御設定

### メインアプリケーション

- `camera/camera_service.py` - PIR センサー統合・ディスプレイ制御
- `scripts/display-brightness.sh` - バックライトの明るさ・電源制御（`camera_service.py` から呼ばれる）

## 🚀 セットアップ手順

### 1. **バックライトの書き込み権限**

**手作業は不要。** `deploy/setup-pi.sh` が `deploy/udev/99-coordinate-backlight.rules` を配置する。

バックライト制御は `sudo` を使わず sysfs を直接書く。権限の内訳は次のとおり。

| ファイル | 誰が開放するか |
|---|---|
| `brightness` | Raspberry Pi OS 標準の `/usr/lib/udev/rules.d/60-backlight.rules`（`chgrp video` + `g+w`） |
| `bl_power` | `deploy/udev/99-coordinate-backlight.rules`（標準 rule が扱わないので足す） |

`unicco` と `coordinate-camera.service`（`SupplementaryGroups=video`）はどちらも `video` グループに属するため、これで書ける。

`sudo` が残るのは `shutdown -h now`（idle auto-shutdown）だけ。`NOPASSWD: ALL` を狭めない判断と将来の前提は [`deploy/docs/pi-sudo-policy.md`](../../deploy/docs/pi-sudo-policy.md)。

### 2. **Kiosk サービス設定**

unit は `systemd/coordinate-kiosk.service`（`Requires=graphical.target` の **system unit**）。`deploy/setup-pi.sh` が `/etc/systemd/system/` に配置し、`graphical.target` が使えるときだけ enable・start する。

```bash
cd ~/coordinate-recorder
bash deploy/setup-pi.sh
```

### 3. **PIR センサー有効化**

<!-- verify: systemd/coordinate-camera.service 2026-07-29 -->

PIR の既定値は `systemd/coordinate-camera.service` に焼き込んである。SD を作り直しても効くように unit 側を正とし、`.env` は上書きが要るときだけ書く。

```
PIR_ENABLED=true
PIR_GPIO_PIN=18
PIR_DETECTION_THRESHOLD=2
PIR_DETECTION_WINDOW=10
PIR_INACTIVITY_TIMEOUT=7
```

**`PIR_DETECTION_WINDOW` を 3 に戻さないこと。** 検知が 6〜9 秒間隔で来るため「3 秒に 2 回」を満たせず、点灯しない・ムラが出る。

### 4. **システム起動時の自動実行**

Pi で自動起動するのはカメラと Kiosk と PIR モニターだけ。API・UI・DB は VPS 側にある。

```
coordinate-camera.service
coordinate-kiosk.service
kiosk-health-monitor.service
camera-pir-monitor.service
```

## 🔄 動作フロー

### PIR センサー検知 → ディスプレイ制御

1. **待機状態**: ディスプレイ OFF、PIR センサー監視
2. **モーション検知**: 3秒以内に2回の検知でアクティベート
3. **画面制御**:
   - バックライト OFF（完全な暗転）
   - 既存 Chromium プロセス終了
   - 新しい Chromium kiosk 起動（暗転中）
   - バックライト ON（touchscreen 表示）
4. **タイムアウト**: 5分後に自動的にスリープモードに復帰

### システム起動時の自動復旧

1. **基本チェック**: ネットワーク、ディスプレイシステム、バックライト
2. **サービス起動**: API、Camera、UI サーバー
3. **ヘルスチェック**: 各エンドポイントの応答確認
4. **Kiosk 起動**: touchscreen インターフェース開始

## 🛠️ 管理コマンド

### サービス制御

```bash
# ステータス確認
sudo systemctl status coordinate-kiosk.service

# 手動起動・停止
sudo systemctl start coordinate-kiosk.service
sudo systemctl stop coordinate-kiosk.service

# ログ確認
sudo journalctl -u coordinate-kiosk.service -f
```

### ディスプレイ制御

```bash
# バックライト状態確認
./scripts/display-brightness.sh status

# 手動制御
./scripts/display-brightness.sh bright  # 明るく
./scripts/display-brightness.sh dim    # 暗く
./scripts/display-brightness.sh off    # 完全 OFF
```

### Kiosk 制御

```bash
# Kiosk 起動・停止
./scripts/kiosk-display-manager.sh start
./scripts/kiosk-display-manager.sh stop
./scripts/kiosk-display-manager.sh restart
```

### ヘルスチェック

```bash
# システム全体の健康状態確認
./scripts/startup-health-check.sh

# 個別サービス確認（Pi 上で叩く場合）
curl http://localhost:8001/health          # Camera（Pi）
curl https://coordinate.unicco.app/health  # API + UI（VPS）
```

## 🔧 トラブルシューティング

### バックライト制御が効かない場合

```bash
# デバイス確認。brightness と bl_power が group=video・g+w になっているか
ls -la /sys/class/backlight/*/
./scripts/display-brightness.sh status
```

### 「Cannot write to ...」と言われる場合

udev rule が当たっていない。`bl_power` だけ書けないなら `99-coordinate-backlight.rules` が無い。

```bash
ls -la /etc/udev/rules.d/99-coordinate-backlight.rules

# 置き直す（setup-pi.sh が配置と reload・trigger まで実施する）
bash deploy/setup-pi.sh
```

手で当て直すときは `--action=add` を忘れないこと。`udevadm trigger` の既定 action は `change` で、この rule は `ACTION=="add"` なので発火しない。

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --action=add --subsystem-match=backlight
```

### PIR センサーが反応しない場合

```bash
# GPIO 権限確認
sudo usermod -a -G gpio $USER

# シミュレーションモードでテスト
curl -X POST http://localhost:8001/pir/simulate

# PIR 状態確認
curl http://localhost:8001/pir/status
```

### Chromium が起動しない場合

```bash
# プロセス確認
ps aux | grep chromium

# 手動起動テスト
/usr/bin/chromium-browser --kiosk http://localhost:3000/touchscreen

# ディスプレイ環境確認
echo $DISPLAY
echo $WAYLAND_DISPLAY
```

### サービスが自動起動しない場合

```bash
# systemd 状態確認（system unit なので --user は付けない）
systemctl list-unit-files | grep coordinate
sudo systemctl is-enabled coordinate-kiosk.service

# graphical.target が無いと setup-pi.sh は Kiosk を enable しない
systemctl list-units --type=target | grep graphical
```

## 📊 システム監視

### ログファイル

- **Kiosk サービス**: `sudo journalctl -u coordinate-kiosk.service`
- **Camera サービス**: `sudo journalctl -u coordinate-camera.service`
- **Kiosk 死活監視**: `sudo journalctl -u kiosk-health-monitor.service`
- **API サーバー（VPS）**: `journalctl --user -u coordinate-api`

### 監視エンドポイント

- **Camera ヘルス（Pi）**: `http://localhost:8001/health` - PIR/ディスプレイ状態含む
- **API ヘルス（VPS）**: `https://coordinate.unicco.app/health`
- **Touchscreen**: Kiosk が開く URL。`scripts/kiosk-display-manager.sh` を参照

## 🔄 再起動後の動作確認チェックリスト

1. **自動起動確認**

   - [ ] Kiosk サービスが自動起動している
   - [ ] Camera サービスが PIR を監視している
   - [ ] ディスプレイが適切に OFF になっている

2. **PIR センサー動作確認**

   - [ ] PIR センサーに手をかざして反応確認
   - [ ] 2回検知後にディスプレイが ON になる
   - [ ] Touchscreen が正常に表示される

3. **タイムアウト動作確認**
   - [ ] 5分後に自動的にディスプレイが OFF になる
   - [ ] スリープモードに戻る

これで PIR センサー連動の自動ディスプレイ制御が完全に機能し、再起動にも対応したシステムが完成しました。
