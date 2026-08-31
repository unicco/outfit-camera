# ワードローブ非同期処理アーキテクチャ

## 概要

ワードローブ画像アップロード時の重い処理（AI 分析、色抽出）を非同期化し、ユーザー体験を向上させました。2025 年 10 月時点では `issue #1203` で整備した **Cloud Run / Cloud Tasks ベースのパイプライン** が正式ルートであり、本ページの FastAPI `BackgroundTasks` 実装はローカルフォールバックとして維持します。Cloud Pipeine 手順は `docs/deployment/cloud-run-pipeline.md` を参照してください。

## 解決する問題

- 画像アップロード時に色抽出や Jina AI 埋め込み処理で数十秒かかることがある
- 同期処理だとユーザーが長時間待たされる
- 処理中にブラウザがタイムアウトする可能性がある

## アーキテクチャ

### 1. 非同期 API 実装 (`api/app/wardrobe_api_async.py`)

- 画像アップロード後、即座にレスポンスを返す
- 重い処理は FastAPI の `BackgroundTasks` でバックグラウンド実行
- CPU 集約的な処理は `ThreadPoolExecutor` で並列化

### 2. バックグラウンド処理

以下の処理を非同期で実行：

- **色抽出**: 高速モードで主要な色を分析
- **Jina AI 埋め込み**: API キーが設定されている場合のみ実行（30秒タイムアウト付き）

### 3. 処理状態追跡 (`api/app/routers/wardrobe_processing.py`)

- `GET /api/v2/wardrobe/processing/status/{item_id}`: 各処理の完了状態を確認

## 使用方法

### 1. 画像アップロード

```bash
# 画像をアップロード（即座にレスポンスが返る）
curl -X POST http://localhost:8000/api/v2/wardrobe/items/{item_id}/images \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg"

# レスポンス例（即座に返される）
{
  "item_id": "123",
  "uploaded_images": [...],
  "message": "Images uploaded successfully. AI processing started in background."
}
```

### 2. 処理状態の確認

```bash
# 処理状態を確認
curl http://localhost:8000/api/v2/wardrobe/processing/status/{item_id}

# レスポンス例
{
  "item_id": "123",
  "upload_completed": true,
  "color_extraction": "completed",  # または "pending", "failed", "skipped"
  "jina_embedding": "completed",
  "last_updated": "2024-01-01T00:00:10"
}
```

## メリット

1. **レスポンスの高速化**: アップロード完了後、即座にユーザーに応答
2. **タイムアウトの回避**: 長時間の処理でも接続が切れない
3. **並行処理**: 複数の画像アップロードを同時に処理可能
4. **エラー耐性**: 個別の処理が失敗してもアップロード自体は成功

## 実装の詳細

- 既存の同期処理エンドポイントを置き換え、互換性を維持
- データベースセッションはバックグラウンドタスク用に新規作成
- 各処理にタイムアウトとエラーハンドリングを実装
