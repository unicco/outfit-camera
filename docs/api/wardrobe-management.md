# ワードローブ管理機能

このドキュメントでは、ワードローブアイテムの管理機能について説明します。

## 📋 目次

- [基本的なワードローブ操作](#基本的なワードローブ操作)
- [AI 検出とマッチング](#ai-検出とマッチング)
- [埋め込みキャッシュ管理](#埋め込みキャッシュ管理)
- [ワードローブ全削除](#ワードローブ全削除)
- [トラブルシューティング](#トラブルシューティング)

---

## 基本的なワードローブ操作

### アイテム管理

```bash
# アイテム一覧取得
curl "http://localhost:8000/api/v2/wardrobe/items"

# アイテム登録
curl -X POST "http://localhost:8000/api/v2/wardrobe/items" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "白いTシャツ",
    "category": "top",
    "color_primary": "white"
  }'

# アイテム削除
curl -X DELETE "http://localhost:8000/api/v2/wardrobe/items/{item_id}"
```

---

## AI 検出とマッチング

### 衣類検出

```bash
# 写真から衣類を検出
curl -X POST "http://localhost:8000/api/v2/ai/detect" \
  -H "Content-Type: application/json" \
  -d '{"photo_id": "your-photo-id"}'
```

### ワードローブマッチング

```bash
# ワードローブとの類似度マッチング
curl -X POST "http://localhost:8000/api/v2/ai/wardrobe-match" \
  -H "Content-Type: application/json" \
  -d '{"photo_id": "your-photo-id", "top_k": 5}'
```

---

## 埋め込みキャッシュ管理

### キャッシュ更新

ワードローブマッチングで「0 matches」が発生する場合、埋め込みキャッシュの更新が必要です。

```bash
# キャッシュを自動構築（推奨）
curl -X POST "http://localhost:8000/api/v2/ai/wardrobe/refresh-cache"

# 強制的に全キャッシュを再構築
curl -X POST "http://localhost:8000/api/v2/ai/wardrobe/refresh-cache?force_refresh=true"
```

**レスポンス例:**

```json
{
  "success": true,
  "cache_stats": {
    "cached_items": 15,
    "total_api_usage": {
      "prompt_tokens": 1500,
      "total_tokens": 2000
    }
  },
  "processing_time_ms": 5240.2,
  "force_refresh": false
}
```

### コスト管理

- **Jina API 使用料**: 画像 1 枚あたり約 $0.0005-0.001
- **推奨**: 初回は少数のアイテムでテストしてからフル実行

---

## ワードローブ全削除

⚠️ **危険な操作です。すべてのワードローブデータが失われます。**

### API 経由での削除

```bash
# ワードローブアイテムを全削除
curl -X POST "http://localhost:8000/api/v2/ai/wardrobe/clear-all?confirm=true"
```

**レスポンス例:**

```json
{
  "success": true,
  "message": "削除完了: 267 個のアイテムを削除しました",
  "deleted_count": 267
}
```

### スクリプト経由での削除

```bash
# 安全な確認プロンプト付き
python scripts/maintenance/clear_wardrobe.py

# 自動確認モード（CI/CD 用）
python scripts/maintenance/clear_wardrobe.py --auto-confirm
```

### 削除理由

以下の場合にワードローブ削除を検討してください：

1. **コスト削減**: 大量の無効なアイテムがある場合
2. **データクリーンアップ**: 空の画像や重複データが多い場合
3. **テスト環境リセット**: 開発・テスト用のクリーンな状態を作る場合

---

## トラブルシューティング

### よくある問題

#### 1. マッチング結果が 0 件

**症状**: `Found 0 matches for today's photo`

**解決策**:

```bash
# 埋め込みキャッシュを更新
curl -X POST "http://localhost:8000/api/v2/ai/wardrobe/refresh-cache"
```

#### 2. GCS 画像読み込みエラー

**症状**: `Image not found for item: https://storage.googleapis.com/...`

**解決策**:

- GCS の権限設定を確認
- 画像 URL が有効かチェック
- 無効なアイテムは削除または画像を再アップロード

#### 3. API キー不足エラー

**症状**: `Jina API key not provided`

**解決策**:

```bash
# 環境変数を設定
export JINA_API_KEY="your-api-key"
```

### ログ確認

```bash
# API サーバーのログを確認
tail -f api/logs/app.log

# 特定の機能のログをフィルタ
grep "wardrobe" api/logs/app.log
grep "embedding" api/logs/app.log
```

---

## 注意事項

### セキュリティ

- ⚠️ **削除機能**: `confirm=true` パラメーターが必須
- 🔐 **API キー**: Jina API キーは環境変数で管理
- 📝 **ログ**: 削除操作はすべてログに記録

### パフォーマンス

- ⏱️ **埋め込み生成**: 大量のアイテムがある場合は時間がかかります
- 💰 **コスト**: Jina API は従量課金制のため、アイテム数に注意
- 🔄 **キャッシュ**: 一度生成した埋め込みは再利用されます

### 推奨運用

1. **段階的テスト**: 少数のアイテムでテスト後、本格運用
2. **定期クリーンアップ**: 無効なアイテムは定期的に削除
3. **バックアップ**: 重要なワードローブデータはバックアップ推奨
