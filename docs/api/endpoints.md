# API リファレンス

Coordinate Recorder システムの API エンドポイント仕様と使用方法を説明します。

## 📌 現在の実装状況

### API プレフィックス

- **安定版**: `/api/v2/*` - 写真・記録・ワードローブ・AI 関連の統一エンドポイント
- **互換ルート**: `/health`, `/debug/*`, `/camera/*` - 既存クライアント維持のため残存

### エンドポイント使用ガイド

#### 写真管理（推奨）

- ✅ 使用: `/api/v2/upload` - 写真アップロード
- ✅ 使用: `/api/v2/records` - 服装記録取得
- ✅ 使用: `/api/v2/daily-status` - 日次撮影ステータス
- ✅ 使用: `/api/v2/photo/{photo_id}` - 写真データ取得
- ✅ 使用: `/api/v2/photos/{photo_id}` - 写真バイナリ取得

#### ワードローブ管理

- ✅ 使用: `/api/v2/wardrobe/*`

#### レガシーエンドポイント

- ⚠️ 非推奨: `/upload-photo`, `/records`, `/daily-status` など

## Backend API (ポート 8000)

### 基本エンドポイント

#### ヘルスチェック・システム状態

- `GET /health` - システムヘルスチェック
- `GET /debug/photos` - 写真ストレージのデバッグ情報
- `POST /debug/reload-photos` - 写真を再読み込み

#### カメラ・写真関連

- `GET /stream` - ライブカメラストリーム（Camera サービス ポート 8001）
- `POST /capture` - 写真撮影（カメラサービス経由）

### V2 API エンドポイント (/api/v2 プレフィックス) ✅ 実装済

#### 写真管理

- `POST /api/v2/upload` - 写真アップロードと人物検出処理（**`photo_id` で冪等**・後述）
- `GET /api/v2/photos` - 写真一覧取得（limit、date_filter パラメータ）
- `GET /api/v2/photo/{photo_id}` - 写真データ取得（base64）
- `GET /api/v2/photos/{photo_id}` - 写真バイナリ取得（JPEG）
- `GET /api/v2/records` - 服装記録の取得（日付フィルター可）
- `GET /api/v2/records/by-clothing/{clothing_item}` - 特定の服での記録取得
- `DELETE /api/v2/records/no-person` - 人物なし記録の削除
- `DELETE /api/v2/photos/no-person` - 人物なし写真の削除
- `GET /api/v2/dates` - 記録がある日付一覧

#### `POST /api/v2/upload` の冪等性

カメラ形式のファイル名 `photo_YYYYMMDD_HHMMSS.jpg` は `photo_id` になり、**同じ
`photo_id` は 1 度しか受け付けない**。2 回目以降は既存レコードをそのまま返し、
GCS への保存・AI 検出・Google Photos・参加者記録のいずれも再実行しない。

```json
{ "success": true, "duplicate": true, "deleted": false,
  "id": "photo_20260808_112459", "photo_id": "photo_20260808_112459",
  "captured_at": "2026-08-08T12:00:00+09:00", "ai_detection_status": "completed",
  "message": "この写真は既に登録済です" }
```

- **削除済でも新しいレコードは作らない**（`deleted: true` を返す）。作ると、人が消した
  写真が別 ID で蘇る。復活させたいときは `deleted_at` を戻す
- **カメラ形式でないファイル名は毎回 UUID** になるので、同名を続けて上げれば別レコードになる
- ⚠️ **塞いだのは DB レコードだけ。** 同じ `photo_id` の 2 リクエストが同時に走ると、
  GCS には両方が同じキーに書く（後勝ち）。**塞がないと決めた**: 同時に
  通りうる 2 経路はどちらもカメラの同じファイルを送るので中身が一致し、上書きしても
  保存画像は変わらない

#### `POST /api/v2/upload` の Form フィールド

| フィールド | 必須 | 用途 |
|---|---|---|
| `file` | ✅ | 画像本体 |
| `original_filename` | | `photo_id` の決定に使う。省略時は `file` のファイル名 |
| `captured_date` | | `YYYY-MM-DD`。渡さないと**受信時刻**で記録される（後日の再送で要注意） |
| `source` | | 届いた経路。`touchscreen` / `camera_retry` / `upload` |

`source` は `Photo.source` にそのまま入る。送り手は 3 つ:

| 送り手 | 送る値 | 意味 |
|---|---|---|
| タッチスクリーン UI | `touchscreen` | 撮って保存ボタンを押した通常経路 |
| Pi の再送ループ | `camera_retry` | UI の送信が失敗したぶんを拾い直した |
| 手動アップロード UI | 送らない → `upload` | 手元の写真を上げた |

知らない値は 400 にせず `upload` として記録する（経路のラベルが読めないだけで、
撮り直しの効かない写真を失わせない）。受け付ける値は `app.routers.upload.UPLOAD_SOURCES`。

#### ステータス・統計

- `GET /api/v2/daily-status` - 日次撮影ステータスと履歴
- `POST /api/v2/daily-reset` - 今日の撮影ステータスをリセット
- `GET /api/v2/capture-required` - 今日の撮影が必要かチェック
- `GET /api/v2/stats` - システム統計情報

### ワードローブ管理 API ✅ 実装済

#### プロキシ経由アクセス（推奨）

- `GET /api/v2/wardrobe/items` - 衣類アイテム一覧
- `POST /api/v2/wardrobe/items` - 新規衣類アイテム作成
- `GET /api/v2/wardrobe/items/{item_id}` - 特定アイテムの詳細取得
- `PUT /api/v2/wardrobe/items/{item_id}` - アイテム情報更新
- `DELETE /api/v2/wardrobe/items/{item_id}` - アイテム削除（ソフトデリート）
- `POST /api/v2/wardrobe/items/{item_id}/images` - アイテムに画像アップロード
- `GET /api/v2/wardrobe/analytics/stats` - ワードローブ統計

### レガシーエンドポイント ⚠️ 非推奨

#### 写真関連（V2 版の使用を推奨）

- `POST /upload-photo` - 廃止 → `/api/v2/upload`
- `GET /photo/{photo_id}` - 廃止 → `/api/v2/photo/{photo_id}`
- `GET /photos/{photo_id}` - 廃止 → `/api/v2/photos/{photo_id}`
- `GET /records` - 廃止 → `/api/v2/records`
- `GET /daily-status` - 廃止 → `/api/v2/daily-status`

#### テスト用

- `POST /test/create-mock-data` - テストデータ作成

#### 静的ファイル

- `/static/photos/*` - 写真ファイルへの静的アクセス

## Camera サービス (ポート 8001)

### 基本エンドポイント ✅ 実装済

- `POST /capture` - 通常の服装写真撮影（モーション検知による自動撮影）
- `GET /health` - ヘルスチェック
- `GET /stream` - カメラのライブストリーミング（MJPEG形式）

### PIR センサー・リアルタイム通信 ✅ 実装済

- `GET /pir/status` - PIR センサー状態の定期取得（500ms 間隔）
- `POST /pir/simulate` - PIR センサーのシミュレーション
- `POST /pir/reset` - PIR センサー状態のリセット
- TouchscreenApp で人物検出のリアルタイム監視を実装

## 使用方法

### 推奨される API 使用パターン

#### 写真撮影・記録フロー

1. UI → Camera: `POST /capture` で撮影。Camera は写真をローカルに保存して未送信の印を
   残すだけで、**自分では送らない**（アップロードは UI が担う）
2. UI → Backend: UI が撮影された写真を取得して `/api/v2/upload` へ送信（`source=touchscreen`）
3. Backend → UI: 保存された写真データを返す

UI が送れないまま終わった写真は、Camera の再送ループが `/api/v2/upload` へ送る
（`source=camera_retry`）。再送はカメラが保存したファイル名をそのまま送るので
`photo_id` が一致し、UI と再送で二重に届いてもレコードは 1 件（前述の冪等性）。

#### ワードローブアイテム管理

1. アイテム一覧取得: `GET /api/v2/wardrobe/items`
2. 新規アイテム作成: `POST /api/v2/wardrobe/items`
3. 画像アップロード: `POST /api/v2/wardrobe/items/{item_id}/images`

#### Google Photos 連携

1. 認証状態確認: `GET /api/v2/google-photos/auth-status`
2. 認証 URL 取得: `GET /api/v2/google-photos/auth-url`
3. 認証コールバック: `GET /api/v2/google-photos/oauth2callback`
4. 認証解除: `POST /api/v2/google-photos/logout`
5. 写真アップロード: `POST /api/v2/google-photos/upload`

## データ形式

### カテゴリ定義

- OUTERWEAR（アウター）
- TOPS（トップス）
- BOTTOMS（ボトムス）
- FOOTWEAR（靴）
- ACCESSORIES（アクセサリー）
- UNDERWEAR（下着）
- BAGS（バッグ）
- OTHER（その他）

### ステータス定義

- ACTIVE（使用中）
- RETIRED（引退）

### 日付フィルター形式

- 形式: `YYYY-MM-DD`
- 例: `/v2/photos?date_filter=2024-06-09`
