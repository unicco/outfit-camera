# Scripts Directory Structure

UI のビルドは `ui/` で `npm run build` するだけ（出力は `ui/dist/`）。Caddy がそのディレクトリを静的配信する。nginx 時代の `/var/www/coordinate-recorder-ui/` 向けビルドスクリプトは削除済。

## ディレクトリ構成

### `/scripts/launch/`

開発環境の統合起動・管理スクリプト群

- `start-development.sh` - すべてのサービスを統合起動
- `services/` - 個別サービス起動モジュール
  - `start-api.sh` - API サーバー起動
  - `start-camera.sh` - カメラサービス起動（環境変数完全サポート）
  - `start-ui.sh` - UI サーバー起動
- `common/` - 共通ユーティリティ
  - `load-env.sh` - 環境変数読み込み
  - `chrome-profile-fix.sh` - Chrome プロファイル競合解決

### `/scripts/setup/`

環境構築・初期設定スクリプト

- `setup-venv-deployment.sh` - Python 仮想環境の作成・管理と依存関係の自動インストール（externally-managed-environment エラーが出たら実行）
- `update-systemd-services.sh` - systemd サービスの仮想環境パス自動更新
- `install-camera-systemd.sh` - systemd サービスとしてカメラを登録
- `setup-display.sh` - ディスプレイ設定
- その他セットアップスクリプト

### `/scripts/debug/`

デバッグ・診断用スクリプト

- `start-simple-camera.sh` - カメラサービス単独起動（デバッグ用）
- `diagnose-camera-issue.sh` - カメラサービスの問題診断
- `restart-camera-force.sh` - カメラサービス強制再起動

### ルートレベルスクリプト

#### 基本起動・停止

- `start-development.sh` - 開発環境起動（`scripts/launch/start-development.sh` へのシンボリックリンク）
- `stop-development.sh` - すべてのサービス停止

#### デプロイメント

- `deploy-production.sh` - 本番環境への統一デプロイスクリプト（Issue #246 対応）

Pi へのデプロイは `.github/workflows/deploy-raspberry-pi.yml` が Tailscale SSH 経由で `deploy/setup-pi.sh` を実行する。手動デプロイ用スクリプトは置かない。

#### systemd 関連

- `systemd-camera-wrapper.sh` - systemd 用ラッパー
- `startup-health-check.sh` - 起動時ヘルスチェック（systemd サービスから使用）
- `monitor-pir-health.sh` - PIR センサー監視（systemd サービスから使用）
- `monitor-camera-health.sh` - カメラサービス内蔵ヘルスモニタリング（systemd サービス内で並行実行）
- `kiosk-display-manager.sh` - Kiosk ディスプレイ管理（systemd サービスから使用）

#### その他ユーティリティ

- `health-check.sh` - API/Camera/UI サービスの動作確認（単体実行、デプロイ後の確認、定期監視）
- `display-brightness.sh` - ディスプレイ輝度調整
- `switch-env.sh` - 環境切り替え

## 使い分け

### 開発環境

```bash
# すべてのサービスを起動
./scripts/start-development.sh

# カメラサービスのみ起動（開発用）
./scripts/launch/services/start-camera.sh
```

### 本番環境（Raspberry Pi）

```bash
# 仮想環境のセットアップと依存関係インストール
./scripts/setup/setup-venv-deployment.sh

# systemd サービスとして管理
sudo systemctl start coordinate-camera

# 統合デプロイメント
./scripts/deploy-production.sh

# ヘルスチェック
./scripts/health-check.sh
```

### トラブルシューティング・デバッグ

```bash
# サービスの動作確認
./scripts/health-check.sh

# 特定サービスのみチェック
./scripts/health-check.sh --api-only
./scripts/health-check.sh --camera-only

# カメラサービス単独起動（デバッグ用）
./scripts/debug/start-simple-camera.sh

# 診断
./scripts/debug/diagnose-camera-issue.sh

# 強制再起動
./scripts/debug/restart-camera-force.sh
```
