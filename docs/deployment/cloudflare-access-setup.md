# Cloudflare Access Google 認証設定ガイド

このドキュメントでは、Cloudflare Access を使用して Google 認証による外部アクセス制御を設定する手順を説明します。

## 📋 概要

Cloudflare Access により、外出時でも安全に coordinate-recorder の Web UI にアクセスできるようになります。

### 設定後のアクセスフロー

1. ユーザーが `https://app.yourdomain.com` にアクセス
2. Cloudflare Access が Google 認証を要求
3. Google アカウントでの認証成功後、Web UI にアクセス可能
4. セッション維持により、一定期間は再認証不要

## 🚀 前提条件

- Cloudflare アカウントの作成・ログイン完了
- ドメインの Cloudflare への追加完了
- Cloudflare Tunnel の設定完了

## 📝 設定手順

### Step 1: Cloudflare Zero Trust ダッシュボードにアクセス

1. [Cloudflare ダッシュボード](https://dash.cloudflare.com/) にログイン
2. 左サイドバーから **Zero Trust** を選択
3. 初回の場合、チーム名を設定（例: `coordinate-recorder-team`）

### Step 2: Google 認証プロバイダーの追加

1. **Settings** → **Authentication** → **Login methods** に移動
2. **Add new** をクリック
3. **Google** を選択
4. 以下の情報を入力：

```
Name: Google OAuth
App ID: (Google Cloud Console で取得した Client ID)
Client Secret: (Google Cloud Console で取得した Client Secret)
```

#### Google OAuth 設定の準備

Google Cloud Console での設定が必要です：

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. プロジェクトを選択または作成
3. **APIs & Services** → **Credentials** に移動
4. **Create Credentials** → **OAuth 2.0 Client IDs** を選択
5. **Application type**: Web application
6. **Authorized redirect URIs** に以下を追加：
   ```
   https://yourdomain.cloudflareaccess.com/cdn-cgi/access/callback
   ```
   （`yourdomain` は実際のドメインに置き換え）

### Step 3: アプリケーションの作成

1. **Access** → **Applications** に移動
2. **Add an application** をクリック
3. **Self-hosted** を選択

#### メインアプリケーション設定

```yaml
Application name: Coordinate Recorder - Main App
Subdomain: app
Domain: yourdomain.com
```

**Policies** セクション:

- **Policy name**: Google Users Only
- **Action**: Allow
- **Assign a group**: Create new group
  - **Group name**: Authorized Users
  - **Defining criteria**:
    - Selector: Emails
    - Value: your-email@gmail.com （許可するGoogle アカウント）

#### API アプリケーション設定

```yaml
Application name: Coordinate Recorder - API
Subdomain: api
Domain: yourdomain.com
```

同様のポリシーを適用

#### カメラアプリケーション設定

```yaml
Application name: Coordinate Recorder - Camera
Subdomain: camera
Domain: yourdomain.com
```

同様のポリシーを適用

### Step 4: セッション設定

各アプリケーションの **Settings** で以下を設定：

```yaml
Session Duration: 24h （24時間）
Auto-redirect to identity provider: Enable
Enable App Launcher: Disable （プライベートアプリのため）
```

### Step 5: 高度なセキュリティ設定（オプション）

#### IP 制限の追加

より高いセキュリティが必要な場合：

1. **Policy** に追加条件を設定
2. **Require** → **IP ranges**
3. 許可する IP 範囲を指定

#### デバイス制限

1. **Settings** → **Device enrollment**
2. **Device enrollment permissions** を設定
3. 特定のデバイスのみアクセス許可

## 🔧 設定例

### 基本設定（個人利用）

```yaml
# アプリケーション設定
Applications:
  - name: "Coordinate Recorder Main"
    domain: "app.yourdomain.com"
    policies:
      - name: "Personal Access"
        action: "Allow"
        rules:
          - email: "your-email@gmail.com"
        session_duration: "24h"

# 認証プロバイダー
Identity Providers:
  - type: "Google"
    name: "Google OAuth"
    config:
      client_id: "your-google-client-id"
      client_secret: "your-google-client-secret"
```

### 家族利用設定

```yaml
policies:
  - name: "Family Access"
    action: "Allow"
    rules:
      - email: "user1@gmail.com"
      - email: "user2@gmail.com"
      - email: "user3@gmail.com"
    session_duration: "12h"
```

## ✅ 動作確認

### 1. 基本アクセステスト

```bash
# 外部ネットワークから実行
curl -I https://app.yourdomain.com
```

期待する結果: HTTP 302 リダイレクト（認証ページへ）

### 2. 認証フローテスト

1. ブラウザで `https://app.yourdomain.com` にアクセス
2. Google 認証画面が表示されることを確認
3. 許可されたアカウントでログイン
4. Web UI にリダイレクトされることを確認

### 3. API アクセステスト

```bash
# 認証後のセッションでテスト
curl -b cookies.txt https://api.yourdomain.com/health
```

## 🛠️ トラブルシューティング

### 認証ループが発生する場合

**原因**: OAuth リダイレクト URI の設定ミス

**解決方法**:

1. Google Cloud Console の OAuth 設定を確認
2. リダイレクト URI が正確に設定されているか確認
3. Cloudflare Access のコールバック URL と一致するか確認

### アクセスが拒否される場合

**原因**: ポリシー設定の問題

**解決方法**:

1. Cloudflare Access のポリシー設定を確認
2. 許可されたメールアドレスが正しく設定されているか確認
3. アプリケーションとポリシーの関連付けを確認

### セッションがすぐに切れる場合

**原因**: セッション設定の問題

**解決方法**:

1. セッション期間の設定を確認
2. Cookie 設定を確認
3. ブラウザの Cookie 設定を確認

## 📱 モバイルアクセス

### iOS Safari での設定

1. **設定** → **Safari** → **詳細** → **JavaScript** を有効化
2. **プライベートブラウジング** をオフにする
3. Cookie を許可する設定にする

### Android Chrome での設定

1. **設定** → **サイトの設定** → **Cookie** を許可
2. **JavaScript** を有効化
3. **サードパーティの Cookie** を許可

## 🔒 セキュリティのベストプラクティス

### 推奨設定

1. **セッション期間**: 12-24時間（用途に応じて調整）
2. **許可ユーザー**: 必要最小限に限定
3. **ログ監視**: Access ログの定期確認
4. **定期見直し**: 月1回の設定見直し

### セキュリティチェックリスト

- [ ] 許可ユーザーリストの最新化
- [ ] 不要なセッションの削除
- [ ] ログの異常なアクセスパターンチェック
- [ ] Google アカウントの2要素認証有効化
- [ ] 定期的なパスワード変更

## 📊 監視とログ

### アクセスログの確認

1. **Logs** → **Access requests** でアクセス履歴を確認
2. 異常なアクセスパターンがないかチェック
3. 認証失敗の回数を監視

### アラート設定

重要なイベントのアラート設定：

1. **Settings** → **Notifications**
2. 以下のイベントでアラート設定：
   - 認証失敗の多発
   - 新しい IP からのアクセス
   - 長時間のセッション

## 🔄 メンテナンス

### 定期メンテナンス項目

- **月次**: 許可ユーザーリストの見直し
- **四半期**: セキュリティポリシーの見直し
- **半年**: Google OAuth 設定の更新確認
- **年次**: 全体設定の見直しと最適化

この設定により、安全で便利な外部アクセス環境が構築できます。
