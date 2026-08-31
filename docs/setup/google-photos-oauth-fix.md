# Google Photos OAuth 2.0 エラー修正ガイド

## エラー: "You can't sign in to this app because it doesn't comply with Google's OAuth 2.0 policy"

このエラーは、Google のセキュリティポリシーに準拠していない設定が原因です。

## 原因

Google OAuth 2.0 は以下のセキュリティ要件があります：

1. **本番環境では HTTPS が必須**

   - `http://pi-camera.local:8000` は許可されません
   - `localhost` または `127.0.0.1` のみ HTTP が許可されます

2. **承認済リダイレクトURI の厳密な一致**
   - Google Cloud Console で設定した URI と完全一致が必要

## 解決方法

### 方法1: localhost を使用（推奨）

1. **SSH ポートフォワーディングを設定**

   ```bash
   # ローカルマシンから実行
   ssh -L 8000:localhost:8000 user@pi-camera.local
   ```

2. **localhost で認証URLを取得**

   ```bash
   # 別のターミナルで実行
   curl -s "http://localhost:8000/google-photos/auth-url?redirect_uri=http://localhost:8000/google-photos/oauth2callback" | python3 -m json.tool
   ```

3. **ブラウザで `http://localhost:8000` 経由でアクセス**

### 方法2: Cloudflare Tunnel を使用（HTTPS）

Cloudflare Tunnel が設定されている場合：

1. **HTTPS URLで認証**

   ```bash
   curl -s "http://localhost:8000/google-photos/auth-url?redirect_uri=https://coordinate.unicco.app/google-photos/oauth2callback" | python3 -m json.tool
   ```

2. **ブラウザで HTTPS URL を使用**

### 方法3: Google Cloud Console の設定変更

1. [Google Cloud Console](https://console.cloud.google.com) にアクセス
2. プロジェクトを選択
3. 「APIとサービス」→「認証情報」
4. OAuth 2.0 クライアントIDを編集
5. 承認済リダイレクトURIに以下を追加：
   - `http://localhost:8000/google-photos/oauth2callback`
   - `http://127.0.0.1:8000/google-photos/oauth2callback`
   - `https://coordinate.unicco.app/google-photos/oauth2callback` (Cloudflare使用時)

## 簡易手順（SSH ポートフォワーディング）

### ステップ1: SSHトンネルを作成

```bash
# ローカルマシンのターミナルで実行
ssh -L 8000:localhost:8000 user@pi-camera.local
```

### ステップ2: 認証を実行

1. ブラウザで `http://localhost:8000/docs` を開く
2. `google-photos` セクションを探す
3. `/google-photos/auth-url` を開いて「Try it out」
4. `redirect_uri` に `http://localhost:8000/google-photos/oauth2callback` を入力
5. 「Execute」をクリック
6. Response から `auth_url` をコピーしてブラウザで開く

### ステップ3: 認証完了を確認

```bash
curl -s http://localhost:8000/google-photos/auth-status | python3 -m json.tool
```

## トラブルシューティング

### エラー: redirect_uri_mismatch

Google Cloud Console の承認済リダイレクトURIを確認し、使用しているURIと完全一致することを確認。

### エラー: invalid_client

OAuth 2.0 クライアントの種類が「ウェブアプリケーション」であることを確認。

### テスト環境での開発

開発中は以下の設定が推奨されます：

1. OAuth 同意画面を「テスト」モードに設定
2. テストユーザーとして自分のGoogleアカウントを追加
3. 本番公開前に Google の審査を受ける
