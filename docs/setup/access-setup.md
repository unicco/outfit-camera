# 外部アクセス設定ガイド

> [!NOTE]
> **この手順は現行構成に当てはまらない**（2026-07-29 確認）。本文が構築する Pi 上の `cloudflared tunnel` は使っていない。`deploy/setup-pi.sh` は `cloudflare-tunnel.service` を廃止対象として停止・削除する。
>
> 現行は VPS の Caddy + Cloudflare Origin Certificate で `coordinate.unicco.app` を公開し、エンドユーザーの認証はエッジの Cloudflare Access が担う。正典は [deploy/caddy/coordinate.caddy](../../deploy/caddy/coordinate.caddy) と [deploy/docs/cloudflare-ingress-firewall.md](../../deploy/docs/cloudflare-ingress-firewall.md)。
>
> 本文は Cloudflare Tunnel 時代の記録として残している。**そのまま実行すると廃止済の構成を再現する。**

外出時に安全に Web UI にアクセスするための Cloudflare Tunnel + Google 認証設定ガイドです。

## 🎯 設定目標

以下の機能を実現します：

- 🌐 **外部からの安全なアクセス**: Google 認証による保護
- 🔒 **ポート開放不要**: Cloudflare Tunnel によるセキュアな接続
- 🆓 **完全無料**: Cloudflare の無料プランで利用可能
- 📱 **マルチデバイス対応**: PC・スマートフォンからアクセス可能

## 🌐 アクセス URL 構成

設定完了後のアクセス URL:

| サービス             | URL                             | 用途                   |
| -------------------- | ------------------------------- | ---------------------- |
| **メインアプリ**     | `https://app.yourdomain.com`    | Web UI メイン画面      |
| **API サーバー**     | `https://api.yourdomain.com`    | REST API・ドキュメント |
| **カメラストリーム** | `https://camera.yourdomain.com` | リアルタイムカメラ配信 |

## 🚀 クイックセットアップ

### 1. Cloudflared インストール

```bash
# Raspberry Pi で実行
# Cloudflared のダウンロード・インストール
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# インストール確認
cloudflared --version
```

### 2. Cloudflare アカウント準備

1. [Cloudflare](https://cloudflare.com) でアカウント作成
2. ドメインを Cloudflare に追加（無料ドメインまたは既存ドメイン）
3. DNS レコードが Cloudflare に移管されていることを確認

### 3. Cloudflare Tunnel 作成

```bash
# Cloudflare にログイン
cloudflared tunnel login

# 新しいトンネル作成
cloudflared tunnel create coordinate-recorder

# 設定ファイル作成
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: coordinate-recorder
credentials-file: /home/pi/.cloudflared/<tunnel-id>.json

ingress:
  # メインアプリ
  - hostname: app.yourdomain.com
    service: http://localhost:3000

  # API サーバー
  - hostname: api.yourdomain.com
    service: http://localhost:8000

  # カメラストリーム
  - hostname: camera.yourdomain.com
    service: http://localhost:8001

  # 最後のルール（必須）
  - service: http_status:404
EOF
```

**注意**: `<tunnel-id>` と `yourdomain.com` を実際の値に置き換えてください。

### 4. DNS レコード設定

```bash
# DNS レコードを自動作成
cloudflared tunnel route dns coordinate-recorder app.yourdomain.com
cloudflared tunnel route dns coordinate-recorder api.yourdomain.com
cloudflared tunnel route dns coordinate-recorder camera.yourdomain.com
```

### 5. Tunnel サービス起動

```bash
# systemd サービス作成
sudo cloudflared service install

# サービス開始・有効化
sudo systemctl start cloudflared
sudo systemctl enable cloudflared

# 状態確認
sudo systemctl status cloudflared
```

## 🔒 Cloudflare Access セキュリティ設定

### 1. Zero Trust ダッシュボードアクセス

1. [Cloudflare ダッシュボード](https://dash.cloudflare.com/) にログイン
2. 左サイドバーから **Zero Trust** を選択
3. チーム名設定（例: `coordinate-recorder-team`）

### 2. Google 認証プロバイダー設定

#### Google Cloud Console での設定

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. **APIs & Services** > **Credentials** に移動
3. **Create Credentials** > **OAuth 2.0 Client ID** を選択

**設定値**:

```
Application type: Web application
Name: Coordinate Recorder Cloudflare Access
Authorized JavaScript origins: https://yourdomain.cloudflareaccess.com
Authorized redirect URIs: https://yourdomain.cloudflareaccess.com/cdn-cgi/access/callback
```

4. Client ID と Client Secret をメモ

#### Cloudflare での設定

1. Zero Trust ダッシュボード > **Settings** > **Authentication**
2. **Add new** > **Google** を選択
3. Google から取得した Client ID・Secret を入力
4. **Save** をクリック

### 3. Access Policy 設定

#### アプリケーション設定

1. **Access** > **Applications** > **Add an application**
2. **Self-hosted** を選択

**設定値**:

```
Application name: Coordinate Recorder
Subdomain: app
Domain: yourdomain.com
Path: (空欄)
```

#### Policy 設定

**Allow Policy の作成**:

```
Policy name: Google Users Only
Action: Allow
Configure rules:
  - Selector: Emails
  - Value: your-email@gmail.com (許可したい Gmail アドレス)
```

同様に `api.yourdomain.com` と `camera.yourdomain.com` のアプリケーションも作成

### 4. セッション設定

**推奨設定**:

```
Session Duration: 24 hours
Refresh Tokens: Enabled
```

## 🔍 動作確認

### 1. ローカル接続確認

```bash
# 各サービスの起動確認
curl -f http://localhost:3000
curl -f http://localhost:8000/health
curl -f http://localhost:8001/stream
```

### 2. Tunnel 接続確認

```bash
# Tunnel 状態確認
cloudflared tunnel info coordinate-recorder

# DNS 確認
nslookup app.yourdomain.com
nslookup api.yourdomain.com
nslookup camera.yourdomain.com
```

### 3. 外部アクセステスト

1. **メインアプリアクセス**: `https://app.yourdomain.com`

   - Google 認証画面が表示されることを確認
   - 認証後に Web UI が表示されることを確認

2. **API アクセステスト**: `https://api.yourdomain.com/health`

   - 認証後に API レスポンスが返ることを確認

3. **カメラストリーム**: `https://camera.yourdomain.com/stream`
   - 認証後にカメラ映像が表示されることを確認

## 🔧 トラブルシューティング

### Tunnel が起動しない

```bash
# ログ確認
sudo journalctl -u cloudflared -f

# 設定ファイル確認
cloudflared tunnel --config ~/.cloudflared/config.yml validate

# 手動起動テスト
cloudflared tunnel --config ~/.cloudflared/config.yml run
```

### DNS 設定の問題

```bash
# DNS 伝搬確認
dig app.yourdomain.com
dig api.yourdomain.com

# Cloudflare DNS レコード確認
# Cloudflare ダッシュボード > DNS タブで確認
```

### 認証が機能しない

1. Google OAuth 設定の確認

   - Authorized URLs が正しく設定されているか
   - Client ID/Secret が正確か

2. Cloudflare Access Policy の確認
   - 正しいメールアドレスが設定されているか
   - Policy が Active になっているか

### パフォーマンスの問題

```bash
# Cloudflare メトリクス確認
cloudflared tunnel metrics

# ローカルサービスの負荷確認
htop
netstat -tuln
```

## 🔒 セキュリティのベストプラクティス

### 1. 認証設定

- **複数要素認証**: Google アカウントで 2FA を有効化
- **セッション管理**: 適切なセッション有効期限設定
- **IP 制限**: 必要に応じて地理的制限を設定

### 2. 監視・ログ

```bash
# アクセスログ監視
tail -f /var/log/cloudflared.log

# 不審なアクセスの監視
# Cloudflare ダッシュボード > Analytics で確認
```

### 3. 定期メンテナンス

- Cloudflared の定期更新
- 認証ポリシーの定期見直し
- アクセスログの定期確認

## 📚 次のステップ

外部アクセス設定が完了したら：

1. 運用監視 で外部からの監視体制構築
2. 定期メンテナンス でセキュリティ更新管理
3. モバイルアプリまたはブックマーク作成で日常利用開始
