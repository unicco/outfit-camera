# systemd サービス設定

このディレクトリには、Coordinate Recorder プロジェクトの systemd サービス設定ファイルが含まれています。

> **重要**: 2025年8月より、本番環境では systemd による管理に完全移行しました。開発用スクリプト（`start-development.sh`、`stop-development.sh`）は廃止予定です。

## サービス一覧

### coordinate-camera.service

カメラサービス（PIR センサー、画像キャプチャ、ストリーミング）を管理します。

- PIR モーション検知
- リアルタイムカメラストリーミング
- 自動画像キャプチャ
- メモリ制限: 512MB
- CPU 使用率: 80%

### coordinate-api.service

FastAPI バックエンドサービスを管理します。

- RESTful API エンドポイント
- データベース接続
- AI 検出処理
- メモリ制限: 1GB
- CPU 使用率: 100%
- 起動前に軽量な依存確認のみ実行（詳細なセットアップは deploy サービスに移譲）

### coordinate-api-deploy.service / coordinate-api-deploy.timer

API 向けの仮想環境セットアップと依存関係インストールを担当します。

- `Type=oneshot` のデプロイ専用サービス
- 共有スクリプト `scripts/setup/setup-venv-deployment.sh --update-deps` を呼び出し
- タイマーが起動後5分で初回実行し、以降は24時間ごとに再実行
- 手動デプロイ時は `sudo systemctl start coordinate-api-deploy` を使用

### coordinate-ui.service

React UI サーバーを管理します。

- 本番環境: ビルド済静的ファイルを配信
- 開発環境: Vite 開発サーバー（ホットリロード対応）
- メモリ制限: 512MB
- CPU 使用率: 80%

### coordinate-kiosk.service

Chromium Kiosk ブラウザを管理します。

- フルスクリーンタッチ UI
- 自動ブライトネス制御
- すべてのサービス起動後に開始
- ヘルスチェック完了を待機
- グラフィカルセッション必須

### coordinate-health-check.service

起動時の統合ヘルスチェックを実行します。

- 全サービスの正常起動確認
- 失敗したサービスの自動再起動
- ネットワーク接続確認
- 一度だけ実行（Type=oneshot）

### coordinate-health-monitor.service / coordinate-health-monitor.timer

API と UI の稼働を定期的に監視し、自動復旧を試みます。

- 10分おきにヘルスチェックを実行
- API/UI の応答がない場合は対象サービスを再起動
- 成功／失敗結果を journal に記録

### camera-pir-monitor.service

PIR センサーの継続的な健康監視を行います。

- カメラサービスの状態監視
- PIR センサーの検知状況確認
- 長時間無検知の検出と対処
- 30秒ごとに自動再起動

### kiosk-health-monitor.service

Kiosk ディスプレイの健康監視を行います。

- Chromium プロセスの監視
- ディスプレイ応答性確認
- 自動復旧機能
- 定期的なヘルスチェック

### coordinate-photo-cleanup.timer / coordinate-photo-cleanup.service

未保存写真の自動クリーニングを行います。

- 毎週日曜日の午前3時に自動実行
- データベースに未登録の古い写真を削除
- デフォルト保持期間: 7日間
- 環境変数で動作をカスタマイズ可能


## デプロイ方法

### 自動デプロイ（推奨）

GitHub Actions により main ブランチへのプッシュ時に自動デプロイされます。

### 手動デプロイ

```bash
# デプロイスクリプトを実行
cd ~/coordinate-recorder
git pull origin main
./systemd/scripts/deploy-services.sh
```

## インストール方法

初回セットアップ時のみ：

```bash
# Pi の unit（このディレクトリ）を配置・有効化する
cd ~/coordinate-recorder
bash deploy/setup-pi.sh
```

VPS の user unit（`coordinate-api` / 各 timer）は `deploy/systemd/` にあり、`bash deploy/setup-vps.sh` が配置する。


## 手動インストール

```bash
# サービス / タイマーファイルをコピー
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/

# systemd をリロード
sudo systemctl daemon-reload

# サービスを有効化
sudo systemctl enable coordinate-api-deploy coordinate-camera coordinate-api coordinate-ui coordinate-health-check coordinate-health-monitor coordinate-kiosk camera-pir-monitor
# タイマーを有効化
sudo systemctl enable coordinate-api-deploy.timer coordinate-health-monitor.timer coordinate-photo-cleanup.timer

# サービスを起動
sudo systemctl start coordinate-api-deploy coordinate-camera coordinate-api coordinate-ui coordinate-health-check coordinate-health-monitor coordinate-kiosk camera-pir-monitor
# タイマーを起動
sudo systemctl start coordinate-api-deploy.timer coordinate-health-monitor.timer coordinate-photo-cleanup.timer
```

## サービス管理コマンド

### 便利スクリプト（推奨）

```bash
# すべてのサービスを起動
./systemd/scripts/start-services.sh

# すべてのサービスを停止
./systemd/scripts/stop-services.sh

# サービスの状態を確認
./systemd/scripts/status-services.sh
```

### 手動管理

```bash
# ステータス確認
sudo systemctl status coordinate-*.service

# ログ表示
sudo journalctl -u coordinate-api-deploy -f
sudo journalctl -u coordinate-camera -f
sudo journalctl -u coordinate-api -f
sudo journalctl -u coordinate-ui -f
sudo journalctl -u coordinate-kiosk -f
sudo journalctl -u coordinate-health-monitor -f

# 再起動
sudo systemctl restart coordinate-api-deploy
sudo systemctl restart coordinate-camera
sudo systemctl restart coordinate-api
sudo systemctl restart coordinate-ui
sudo systemctl restart coordinate-kiosk

# 停止
sudo systemctl stop coordinate-*.service

# 無効化（自動起動を停止）
sudo systemctl disable coordinate-kiosk
```

## トラブルシューティング

### サービスが起動しない

```bash
# 詳細なエラーログを確認
sudo journalctl -u coordinate-api -n 100 --no-pager

# 依存関係を確認
systemctl list-dependencies coordinate-api
```

### Kiosk が表示されない

```bash
# ディスプレイ環境変数を確認
echo $DISPLAY
echo $WAYLAND_DISPLAY

# 手動でテスト
/home/pi/coordinate-recorder/scripts/kiosk-display-manager.sh start
```

## 設定のカスタマイズ

サービスファイルを編集後は、必ず以下を実行：

```bash
# デーモンをリロード
sudo systemctl daemon-reload

# サービスを再起動
sudo systemctl restart [service-name]
```
