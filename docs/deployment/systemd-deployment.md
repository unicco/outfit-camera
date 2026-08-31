# デプロイメントガイド

## 概要

Coordinate Recorder は 2 台構成で運用されます：

| 環境 | 役割 | サービス |
|------|------|----------|
| **Raspberry Pi** | カメラ撮影 | `coordinate-camera.service`（system） |
| **ConoHa VPS** | API + UI + DB | `coordinate-api.service`（user）、ヘルスチェック timer、DB バックアップ timer |

デプロイは GitHub Actions で main マージ時に自動実行されます。手動セットアップが必要な場合は IaC スクリプトを使います。

## 自動デプロイ（GitHub Actions）

### Raspberry Pi

- **トリガー**: `camera/`、`systemd/`、`scripts/monitor-camera-health.sh`、`scripts/display-brightness.sh` の変更
- **ワークフロー**: `.github/workflows/deploy-raspberry-pi.yml`
- **処理**: git pull → `bash deploy/setup-pi.sh` → カメラサービス動作確認

### VPS

- **トリガー**: `api/`、`src/`、`ui/`、`deploy/`、`requirements-api.txt` の変更
- **ワークフロー**: `.github/workflows/deploy-vps.yml`
- **処理**: git pull → `bash deploy/setup-vps.sh` → ヘルスチェック確認

### 接続方式

GitHub Actions → Tailscale → SSH。各環境に composite action がある：
- `.github/actions/setup-pi-ssh/action.yml`
- `.github/actions/setup-vps-ssh/action.yml`

## 手動セットアップ

### Raspberry Pi

```bash
ssh user@pi-camera.local
cd ~/coordinate-recorder
bash deploy/setup-pi.sh
```

`deploy/setup-pi.sh` は冪等で以下を実行：
- 不要な旧サービスの停止・無効化・削除
- `coordinate-camera.service` のインストールと起動
- 旧データ（venv、SQLite DB、nginx 設定、node_modules 等）の削除

### VPS

```bash
ssh deploy@100.64.0.10  # Tailscale 経由
cd ~/services/coordinate-recorder
bash deploy/setup-vps.sh
```

`deploy/setup-vps.sh` は冪等で以下を実行：
- システム依存パッケージ（libgl1 等）のインストール
- Python venv 構築・依存関係インストール
- DB マイグレーション（`alembic upgrade head`）
- UI ビルド（`npm ci && npm run build`）
- systemd サービス・タイマーのインストールと起動
- Caddy + Origin Certificate の検証

## systemd サービス一覧

### Raspberry Pi

| サービス | 種別 | 説明 |
|----------|------|------|
| `coordinate-camera.service` | system | カメラ撮影・PIR センサー検知 |

### VPS

| サービス | 種別 | 説明 |
|----------|------|------|
| `coordinate-api.service` | user | FastAPI サーバー（port 8000） |
| `coordinate-health-check.timer` | user | 5 分間隔のヘルスチェック |
| `coordinate-db-backup.timer` | user | 毎日 03:00 の DB バックアップ |

サービス定義ファイル: `deploy/systemd/`
スクリプト: `deploy/scripts/health-check.sh`、`deploy/scripts/db-backup.sh`

## サービス管理コマンド

### Raspberry Pi

```bash
# 状態確認
sudo systemctl status coordinate-camera

# 再起動
sudo systemctl restart coordinate-camera

# ログ確認
sudo journalctl -u coordinate-camera -f
```

### VPS

```bash
# 状態確認
systemctl --user status coordinate-api
systemctl --user list-timers

# 再起動
systemctl --user restart coordinate-api

# ログ確認
journalctl --user -u coordinate-api -f
journalctl --user -u coordinate-health-check -f
```

## ネットワーク構成

```
[ユーザー] → Cloudflare（DNS + SSL Full Strict）→ VPS Caddy → FastAPI :8000
              coordinate.unicco.app                  Origin Certificate

[Pi Camera] → Tailscale → VPS API :8000（撮影データ送信）

[GitHub Actions] → Tailscale → SSH → Pi / VPS（自動デプロイ）
```

### SSL/TLS

- Cloudflare Origin Certificate（15 年有効）を VPS の Caddy に設置
- Cloudflare SSL モード: Full (Strict)
- 証明書パス: `/etc/caddy/certs/origin.pem`、`/etc/caddy/certs/origin-key.pem`

## トラブルシューティング

### API が起動しない

```bash
# ログを確認
journalctl --user -u coordinate-api -n 50

# Python モジュールエラーの場合
~/services/coordinate-recorder/venv/bin/python -c "import cv2"  # libGL 依存
sudo apt install libgl1 libglib2.0-0
```

### DB バックアップが失敗する

```bash
# バックアップログを確認
journalctl --user -u coordinate-db-backup --since today

# 手動実行
bash deploy/scripts/db-backup.sh
```

### ヘルスチェック

```bash
# API ヘルスチェック
curl -sf http://127.0.0.1:8000/health | python3 -m json.tool

# 外部からの確認
curl -sf https://coordinate.unicco.app/health
```
