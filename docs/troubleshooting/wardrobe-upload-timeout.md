# ワードローブ画像アップロード タイムアウト問題

## 問題の概要

ワードローブ画像アップロード時に、処理時間が 30 秒以上かかることでブラウザのデフォルトタイムアウトが発生し、アップロードが失敗する問題があります。

## 原因

### フロントエンド側

- ワードローブ画像アップロードで AbortController が使用されていない
- ブラウザデフォルトタイムアウト（30-60秒）に依存
- `API_TIMEOUT.FILE_UPLOAD` (30秒) の設定が未適用

### バックエンド側

- Jina AI 埋め込み生成: 最大 60 秒
- 色抽出処理: 1-3 秒
- Phase 2 AI 分析: 5-20 秒
- すべての処理が同期実行される

## 即座に実装可能な解決策

### 1. フロントエンドタイムアウト延長

`ui/src/components/wardrobe/NewItemRegistrationPage.tsx` および `EditItemPage.tsx` で：

```typescript
// 120秒のタイムアウトを設定
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 120000);

try {
  const imageResponse = await fetch(url, {
    method: "POST",
    body: formData,
    signal: controller.signal,
  });
} finally {
  clearTimeout(timeoutId);
}
```

### 2. Uvicorn タイムアウト設定

`scripts/launch/services/start-api.sh` で：

```bash
python -m uvicorn app.main_v2:app \
  --host 0.0.0.0 \
  --port $api_port \
  --timeout-keep-alive 180 \
  --reload
```

## 推奨タイムアウト設定値

| コンポーネント | 設定項目                     | 推奨値 | 理由                              |
| -------------- | ---------------------------- | ------ | --------------------------------- |
| フロントエンド | 画像アップロードタイムアウト | 120秒  | Jina API (60s) + 処理時間余裕     |
| Uvicorn        | keep-alive timeout           | 180秒  | フロントエンドタイムアウト + 余裕 |
| Jina API       | API 呼び出しタイムアウト     | 60秒   | 現状維持（適切）                  |
| Nginx/Apache   | プロキシタイムアウト         | 200秒  | 全体処理時間 + 余裕               |

## 中長期的改善案

### 1. バックグラウンド処理化

- 画像アップロード完了後、即座にレスポンス返却
- AI 分析を非同期タスクとして実行
- WebSocket またはポーリングでステータス通知

### 2. プログレスバー実装

- 処理中の視覚的フィードバック
- ユーザーの不安軽減

### 3. タイムアウト階層化

- フェーズごとのタイムアウト設定
- 部分的成功の許可（例: 色抽出は成功、AI分析は後で実行）

## 関連ファイル

- `/ui/src/config/api.ts` - タイムアウト設定定義
- `/ui/src/components/wardrobe/NewItemRegistrationPage.tsx` - 新規登録画面
- `/ui/src/components/wardrobe/EditItemPage.tsx` - 編集画面
- `api/app/routers/wardrobe.py` - ワードローブ API エンドポイント
- `/src/coordinate_recorder/jina_api_service.py` - Jina API 呼び出し
