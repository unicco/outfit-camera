# 本番デプロイメント実施記録

## 📋 Issue #246: 本番デプロイメント完了

### 実施日時

2025-07-01

### 本番環境

- **サーバー**: pi-camera.local (Raspberry Pi)
- **デプロイ方法**: 直接 Python 実行

## 🚀 実施した作業

### 1. 本番環境デプロイ

```bash
# 本番デプロイ手順
ssh user@pi-camera.local
cd /home/pi/coordinate-recorder
git pull origin main
./scripts/start-development.sh
```

- 直接 Python 実行による本番デプロイ
- 本番環境ヘルスチェック確認

### 2. 依存関係問題修復

#### Camera Service: AI モジュール不足（当時）

```bash
# 問題: ImportError: cannot import name 'YOLO' from 'ultralytics'
# 注: 現在は Roboflow API を使用しているため、この問題は発生しません
# 当時の解決方法:
cd /home/pi/coordinate-recorder
source camera/venv/bin/activate
pip install ultralytics  # 現在は不要
```

#### API Service: google-cloud-storage 不足

```bash
# 問題: GCS_AVAILABLE = False (google.cloud モジュール不足)
# 解決方法:
cd /home/pi/coordinate-recorder
source api/venv/bin/activate
pip install google-cloud-storage
```

### 3. 認証設定修正

#### GCS 認証ファイルパス

```bash
# 修正前: /home/pi/coordinate-recorder/secrets/gcp-key.json
# 修正後: /home/pi/.config/gcloud/service-account-key.json

# api/.env の更新:
GOOGLE_APPLICATION_CREDENTIALS=/home/pi/.config/gcloud/service-account-key.json
```

#### PostgreSQL 認証

```bash
# ユーザー作成とパスワード設定
sudo -u postgres createuser -s unicco
sudo -u postgres psql -c "ALTER USER unicco PASSWORD 'password';"
sudo -u postgres createdb coordinate_recorder -O unicco
```

### 4. ストレージ設定

#### 環境変数設定 (api/.env)

```
STORAGE_TYPE=gcs
GCS_PROJECT_ID=your-gcp-project-id
GCS_BUCKET_NAME=example-wardrobe-prod
GOOGLE_APPLICATION_CREDENTIALS=/home/pi/.config/gcloud/service-account-key.json
DATABASE_MODE=fallback
```

## ✅ 動作確認結果

### 全サービス正常稼働確認

```bash
# API サーバー (port 8000)
curl http://pi-camera.local:8000/health
# → {"status":"ok","model_loaded":true,"ai_detection_v2":true,...}

# Camera サーバー (port 8001)
curl http://pi-camera.local:8001/health
# → {"status":"healthy","camera_mode":"hardware"}

# UI サーバー (port 3000)
curl http://pi-camera.local:3000
# → <title>今日なに着た？</title>
```

### GCS ストレージ統合確認

- 新規ワードローブアイテムが GCS (example-wardrobe-prod) に正常保存
- ローカルファイルフォールバック問題解決

## 📝 今回の学習事項

### 1. 依存関係管理の重要性

- **google-cloud-storage** が requirements に含まれていなかった
- **ultralytics** が Camera service で不足していた（現在は Roboflow API 使用のため不要）
- → **推奨**: pyproject.toml への google-cloud-storage 追加

### 2. 認証ファイル管理

- GCS 認証ファイルの正しいパス設定が重要
- 環境変数での適切な管理が必要

### 3. 統一デプロイメントの価値

- 手動デプロイの混乱を統一スクリプトで解決
- 再現可能で追跡可能なデプロイメント実現

## 🔄 今後の改善点

1. **依存関係の明確化**: 全必要パッケージを pyproject.toml に記載
2. **認証設定の標準化**: デプロイ手順における認証ファイル配置の明文化
3. **自動化の推進**: デプロイメント後の依存関係チェック自動化

## 🎯 Issue #246 解決確認

- ✅ 本番デプロイの混乱解消
- ✅ 統一デプロイメント実装完了
- ✅ 再現可能なデプロイメント確立
- ✅ 全サービス正常稼働確認

**Result**: Issue #246 完全解決

---

## 📦 Issue #1203: Cloud Run パイプライン基盤

### セットアップ概要

- Terraform 定義: `infrastructure/terraform/pipeline/`
- コンテナ: `cloudrun/pipeline_dispatcher/`, `cloudrun/pipeline_runner_stub/`
- Smoke テスト: `scripts/dev/pipeline-smoke-test.sh`

### 適用手順

```bash
cd infrastructure/terraform/pipeline
cp terraform.tfvars.example terraform.tfvars
# project_id / gcs_bucket / image タグを編集
terraform init
terraform apply
```

### 本番/開発の設定値

| 環境 | GCS バケット | 備考 |
| ---- | ------------ | ---- |
| dev  | `.env` の `GCS_BUCKET_NAME` (例: example-wardrobe-dev) | 既存設定を流用 |
| prod | `example-wardrobe-prod` | ユーザー提供の本番バケット |

### 監視とアラート

- Cloud Tasks のキュー長が 100 を超えるとアラートが発火（通知チャネルは別途追加）
- Dispatcher / Runner の ERROR ログを logs-based metric で収集
- Runner スタブが `analysis-complete` Topic まで publish するため、#1204 / #1205 の実装後はスタブから差し替えるだけで可動

### ロールバック手順

1. Terraform `apply` 前に `plan` のバックアップを `terraform.tfplan` として保存
2. 想定外の動作があれば `terraform destroy -target google_cloud_run_v2_service.<name>` 等で段階的に戻す
3. Cloud Tasks キューが暴走した場合は `gcloud tasks queues pause <queue>` で一時停止

### 備考

- Matching 以降のステージは `analysis-complete` Topic から後続 Issue (#1206 以降) で拡張
- Runner スタブはあくまで配線確認用。#1204 / #1205 で実際の処理を実装したら、該当ステージの `*_runner_image` を差し替えて Terraform で更新する
