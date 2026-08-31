# システムセットアップガイド

## システム構成概要

```
[Raspberry Pi 5]                      [ConoHa VPS (Ubuntu)]
  coordinate-camera.service             coordinate-api.service (user)
  - PIR センサー検知                     coordinate-health-check.timer
  - Sony IMX500 カメラ撮影               coordinate-db-backup.timer
  - 撮影画像を VPS API に送信            Caddy + Cloudflare Origin Cert
                                        PostgreSQL
                                        React UI (静的ビルド配信)
```

## Raspberry Pi セットアップ

### 前提条件

- Raspberry Pi OS 64-bit (Debian 12 Bookworm)
- SSH アクセス有効
- Sony IMX500 AI カメラ接続済
- Tailscale インストール済

### セットアップ手順

```bash
# リポジトリクローン
git clone https://github.com/unicco/coordinate-recorder.git ~/coordinate-recorder
cd ~/coordinate-recorder

# 冪等セットアップスクリプト実行
bash deploy/setup-pi.sh

# 確認
sudo systemctl status coordinate-camera
```

`deploy/setup-pi.sh` は以下を実行:
- 1 台構成時代の旧サービス（`coordinate-api` / `coordinate-ui` / `cloudflare-tunnel` / `nginx` / PostgreSQL）を停止・削除
- Kiosk・PIR モニター（`coordinate-kiosk` / `kiosk-health-monitor` / `camera-pir-monitor`）をインストール。Kiosk は `graphical.target` が使えるときだけ起動
- `coordinate-camera.service` をインストール・起動
- 旧データ（venv、SQLite、nginx 等）を削除

### カメラ動作確認

```bash
# カメラデバイスの確認
libcamera-hello --list-cameras

# サービスログ確認
sudo journalctl -u coordinate-camera -f
```

## VPS セットアップ

### 前提条件

- Ubuntu 22.04+
- Tailscale インストール済
- Caddy インストール済
- PostgreSQL インストール済
- Cloudflare Origin Certificate 配置済（`/etc/caddy/certs/`）

### セットアップ手順

```bash
# リポジトリクローン
git clone https://github.com/unicco/coordinate-recorder.git ~/services/coordinate-recorder
cd ~/services/coordinate-recorder

# 環境変数設定
cp .env.template .env
# .env を編集して DATABASE_URL 等を設定

# 冪等セットアップスクリプト実行
bash deploy/setup-vps.sh

# 確認
systemctl --user status coordinate-api
curl -sf http://127.0.0.1:8000/health | python3 -m json.tool
```

`deploy/setup-vps.sh` は以下を実行:
- システム依存パッケージのインストール（libgl1 等）
- Python venv 作成・依存関係インストール
- DB マイグレーション実行
- UI ビルド
- systemd サービス・タイマーのインストール・起動
- Caddy 設定の検証

### Caddy 設定

Caddy は Cloudflare Origin Certificate で TLS を終端します:

```
coordinate.unicco.app {
    tls /etc/caddy/certs/origin.pem /etc/caddy/certs/origin-key.pem
    handle /api/* { reverse_proxy localhost:8000 }
    handle /health { reverse_proxy localhost:8000 }
    handle { root * /path/to/ui/dist; file_server; try_files {path} /index.html }
}
```

### データベース

```bash
# PostgreSQL に coordinate_db を作成
sudo -u postgres createdb coordinate_db

# バックアップ用の読み取り専用ロール（deploy で peer 認証）
sudo -u postgres createuser deploy
sudo -u postgres psql -c "GRANT CONNECT ON DATABASE coordinate_db TO deploy;"
sudo -u postgres psql -d coordinate_db -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO deploy;"
```

## 次のステップ

- [デプロイメントガイド](../deployment/systemd-deployment.md) - サービス管理の詳細
- 監視ガイド - 日常監視
