# Google Photos 認証セットアップガイド

このガイドでは、Coordinate Recorder で Google Photos API の認証を設定する手順を説明します。

## 前提条件

1. Google Cloud Console でプロジェクトを作成済
2. Google Photos Library API を有効化済
3. OAuth 2.0 クライアント認証情報（credentials.json）を取得済

## 認証手順

### 1. 既存のトークンを削除（必要な場合）

```bash
# SSH で Raspberry Pi に接続
ssh user@pi-camera.local

# coordinate-recorder ディレクトリに移動
cd /home/pi/coordinate-recorder

# 既存のトークンを削除
rm -f google_photos_token.json

# API サービスを再起動
sudo systemctl restart coordinate-api
```

### 2. 認証URLの取得

以下のコマンドを実行して、認証用URLを取得します：

```bash
curl -s "http://localhost:8000/google-photos/auth-url?redirect_uri=http://pi-camera.local:8000/google-photos/oauth2callback" | python3 -m json.tool
```

**重要**: リダイレクトURIは環境に応じて変更してください：

- ローカル開発: `http://localhost:8000/google-photos/oauth2callback`
- Raspberry Pi: `http://pi-camera.local:8000/google-photos/oauth2callback`
- Cloudflare Tunnel使用時: `https://your-domain.com/google-photos/oauth2callback`

### 3. ブラウザで認証

1. 上記コマンドの出力から `auth_url` の値をコピー
2. ブラウザで該当URLを開く
3. Google アカウントでログイン
4. 以下の権限を許可：
   - Google フォト ライブラリの表示、アップロード、整理
   - Google フォト ライブラリへの追加
   - あなたが作成した Google フォト内のアイテムの共有の編集
   - Google カレンダーの予定の表示 (`https://www.googleapis.com/auth/calendar.readonly`)

### 4. 認証完了の確認

認証が成功すると、自動的にリダイレクトされ、トークンが保存されます。

確認方法：

```bash
# 認証状態を確認
curl -s http://localhost:8000/google-photos/auth-status | python3 -m json.tool
```

成功時の出力例：

```json
{
  "is_authenticated": true,
  "album_name": "Coordinate Records"
}
```

## トラブルシューティング

### "Authentication completion failed" エラー

**原因**: リダイレクトURIの不一致

**解決方法**:

1. Google Cloud Console で設定した承認済リダイレクトURIを確認
2. 認証URL取得時に正しいリダイレクトURIを指定

### "Request had insufficient authentication scopes" エラー

**原因**: 古いスコープでトークンが生成されている

**解決方法**:

1. 既存のトークンを削除
2. 最新のコードを取得（PR #916 のマージ後）
3. 再認証を実行

### リダイレクトURIの設定

Google Cloud Console で以下のURIを承認済リダイレクトURIに追加：

- `http://localhost:8000/google-photos/oauth2callback`
- `http://localhost:8080/oauth2callback`
- `http://pi-camera.local:8000/google-photos/oauth2callback`
- `https://your-domain.com/google-photos/oauth2callback` (Cloudflare使用時)

## 環境変数の設定（オプション）

`.env` ファイルで以下を設定できます：

```bash
# Google Photos 設定
GOOGLE_PHOTOS_ENABLED=true
GOOGLE_CREDENTIALS_FILE=google_photos_credentials.json
GOOGLE_TOKEN_FILE=google_photos_token.json
GOOGLE_PHOTOS_ALBUM_NAME=Coordinate Records
GOOGLE_REDIRECT_BASE_URL=http://pi-camera.local:8000

# Google Calendar 設定
GOOGLE_CALENDAR_DELEGATED_USER=user@example.com
GOOGLE_CALENDAR_PRIMARY_ID=primary
GOOGLE_CALENDAR_EXTRA_IDS=team_calendar_id,personal_events_id
```

## Discord 通知による失効アラート

Raspberry Pi 上では `coordinate-health-monitor` タイマーが 10 分間隔で認証状態を監視しています。  
`.env` に `DISCORD_ALERT_WEBHOOK_URL`（必要に応じて `DISCORD_ALERT_MENTION` や `DISCORD_ALERT_USERNAME`）を設定すると、トークンが失効した際に Discord にアラートが送信されます。認証が回復するとキャッシュがクリアされ、次回の失効時に再び通知が届きます。

## セキュリティに関する注意

- `google_photos_credentials.json` と `google_photos_token.json` は機密情報です
- これらのファイルをGitにコミットしないでください
- 適切なファイル権限を設定してください：
  ```bash
  chmod 600 google_photos_*.json
  ```
