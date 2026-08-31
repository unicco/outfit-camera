# Kiosk Scripts ガイド

本番機でのキオスク（Chromium 全画面表示）管理スクリプトの使用方法

## 推奨スクリプト（使用推奨）

### 1. メインキオスク管理

- **`kiosk-display-manager.sh`** ⭐ - メインのキオスク表示管理スクリプト
  ```bash
  ./kiosk-display-manager.sh start    # 基本起動
  ./kiosk-display-manager.sh stop     # 停止
  ./kiosk-display-manager.sh restart  # 再起動
  ```

### 2. systemd サービス

<!-- verify: systemd/coordinate-kiosk.service 2026-07-29 -->

- **`coordinate-kiosk.service`** ⭐ - メイン systemd サービス。`kiosk-display-manager.sh start` / `stop` を呼ぶだけの薄い unit
- **`kiosk-health-monitor.service`** - 表示の死活監視（`systemd/scripts/kiosk-health-monitor.sh`）

どちらも `deploy/setup-pi.sh` が `/etc/systemd/system/` に配置する **system unit**（`Requires=graphical.target`）。`--user` では動かない。

## 統合済機能

以下の機能は既に `kiosk-display-manager.sh` に統合されています：

- 手動フルスクリーン起動
- サービス依存待機機能
- 自動ブラウザ起動

## 使用方法

### 基本的なキオスク起動

```bash
# 1. メインスクリプトで起動
./scripts/kiosk-display-manager.sh start

# 2. systemd サービスで起動
sudo systemctl start coordinate-kiosk.service
```

### 自動起動設定

個別に enable せず `deploy/setup-pi.sh` に任せる。`graphical.target` が使えるときだけ enable・start される。

```bash
cd ~/coordinate-recorder
bash deploy/setup-pi.sh

sudo systemctl status coordinate-kiosk
sudo journalctl -u coordinate-kiosk -f
```

## ファイル構造

```
scripts/
└── kiosk-display-manager.sh           # メインキオスク管理 ⭐
systemd/
├── coordinate-kiosk.service           # メインサービス ⭐
├── kiosk-health-monitor.service       # 表示の死活監視
└── scripts/
    └── kiosk-health-monitor.sh        # 監視本体
```

## 推奨使用方法

メインキオスク管理機能を使用してください：

- **キオスク起動**: `./scripts/kiosk-display-manager.sh start`

## トラブルシューティング

### よくある問題

1. **Chromium が起動しない**

   ```bash
   ./scripts/kiosk-display-manager.sh restart
   ```

2. **サービス依存の問題**

   ```bash
   sudo systemctl status coordinate-kiosk.service
   sudo journalctl -u coordinate-kiosk.service -f
   ```

3. **権限の問題**
   ```bash
   chmod +x scripts/*.sh
   ```
