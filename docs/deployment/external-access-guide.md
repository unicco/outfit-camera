# 外部アクセス設定ガイド - Cloudflare Tunnel + Google 認証

外出時に安全に coordinate-recorder Web UI にアクセスするための設定ガイドです。

## 📋 概要

この設定により、以下が実現できます：

- 🌐 **外部からの安全なアクセス**: Google 認証による保護
- 🔒 **ポート開放不要**: Cloudflare Tunnel によるセキュアな接続
- 🆓 **完全無料**: Cloudflare の無料プランで利用可能
- ⚡ **簡単設定**: 約1時間で完了
- 📱 **マルチデバイス対応**: PC・スマートフォンからアクセス可能

## 🎯 アクセス URL

設定完了後のアクセス URL:

| サービス             | URL                             | 用途                   |
| -------------------- | ------------------------------- | ---------------------- |
| **メインアプリ**     | `https://app.yourdomain.com`    | Web UI メイン画面      |
| **API サーバー**     | `https://api.yourdomain.com`    | REST API・ドキュメント |
| **カメラストリーム** | `https://camera.yourdomain.com` | リアルタイムカメラ配信 |

## 🚀 クイックスタート

### 1. Cloudflared インストール

```bash
# Raspberry Pi で実行
./scripts/setup/install-cloudflared.sh
```

### 2. Cloudflare Tunnel 設定

```bash
# 対話形式で設定
./scripts/setup/setup-cloudflare-tunnel.sh
```

### 3. systemd サービス設定

```bash
# 自動起動設定
sudo ./scripts/setup/setup-cloudflare-systemd.sh
```

### 4. Cloudflare Access 認証設定

[Cloudflare Access 設定手順](./cloudflare-access-setup.md) を参照して Google 認証を設定

### 5. 動作確認

```bash
# 外部アクセステスト実行
./scripts/debug/test-external-access.sh yourdomain.com
```

## 📋 詳細設定手順

### Step 1: 前提条件確認

- [ ] Cloudflare アカウント作成済
- [ ] ドメイン取得済 (既存ドメインまたは Cloudflare 提供サブドメイン)
- [ ] Raspberry Pi でサービス稼働中 (UI, API, Camera)

### Step 2: Cloudflared インストール

```bash
cd /path/to/coordinate-recorder
./scripts/setup/install-cloudflared.sh
```

**確認項目:**

- [ ] cloudflared バイナリインストール完了
- [ ] cloudflared ユーザー作成完了
- [ ] 設定ディレクトリ作成完了

### Step 3: Tunnel 作成と設定

```bash
# 環境変数でドメイン指定（推奨）
export CLOUDFLARE_DOMAIN="yourdomain.com"
./scripts/setup/setup-cloudflare-tunnel.sh
```

**設定内容:**

- [ ] Cloudflare 認証完了
- [ ] Tunnel `coordinate-recorder` 作成完了
- [ ] DNS レコード設定完了:
  - `app.yourdomain.com`
  - `api.yourdomain.com`
  - `camera.yourdomain.com`
- [ ] 設定ファイル `/etc/cloudflared/config.yml` 作成完了

### Step 4: systemd サービス設定

```bash
sudo ./scripts/setup/setup-cloudflare-systemd.sh
```

**確認項目:**

- [ ] systemd サービスファイル作成完了
- [ ] サービス有効化・起動完了
- [ ] サービス状態確認: `sudo systemctl status cloudflare-tunnel`

### Step 5: Cloudflare Access 認証設定

詳細は [Cloudflare Access 設定ガイド](./cloudflare-access-setup.md) を参照

**必要な設定:**

- [ ] Google OAuth プロバイダー追加
- [ ] 各サブドメインにアプリケーション作成
- [ ] アクセスポリシー設定 (許可ユーザー)
- [ ] セッション期間設定

### Step 6: 動作確認とテスト

```bash
# 包括的なテスト実行
./scripts/debug/test-external-access.sh yourdomain.com
```

**テスト項目:**

- [ ] DNS 解決確認
- [ ] SSL 証明書確認
- [ ] HTTP 接続確認
- [ ] Cloudflare 経由確認
- [ ] ローカルサービス確認

## 🔧 設定ファイル

### Cloudflare Tunnel 設定 (`/etc/cloudflared/config.yml`)

```yaml
tunnel: <tunnel-id>
credentials-file: /etc/cloudflared/coordinate-recorder.json

ingress:
  # メインアプリ (React UI)
  - hostname: app.yourdomain.com
    service: http://localhost:3000

  # API サーバー
  - hostname: api.yourdomain.com
    service: http://localhost:8000

  # カメラストリーム
  - hostname: camera.yourdomain.com
    service: http://localhost:8001

  # デフォルト
  - service: http://localhost:3000

loglevel: info
retries: 3
grace-period: 30s
```

### systemd サービス設定

サービス名: `cloudflare-tunnel.service`

**管理コマンド:**

```bash
# 状態確認
sudo systemctl status cloudflare-tunnel

# 開始・停止・再起動
sudo systemctl start cloudflare-tunnel
sudo systemctl stop cloudflare-tunnel
sudo systemctl restart cloudflare-tunnel

# ログ確認
sudo journalctl -u cloudflare-tunnel -f
```

## 🛠️ トラブルシューティング

### 一般的な問題と解決方法

#### 1. DNS 解決に失敗する

**原因**: DNS レコードの未設定または伝播待ち

**解決方法:**

```bash
# DNS 確認
nslookup app.yourdomain.com

# Cloudflare で DNS レコード再設定
cloudflared tunnel route dns coordinate-recorder app.yourdomain.com
```

#### 2. 接続がタイムアウトする

**原因**: ローカルサービス停止または Tunnel 接続問題

**解決方法:**

```bash
# ローカルサービス確認
./scripts/start-development.sh

# Tunnel サービス確認
sudo systemctl restart cloudflare-tunnel
sudo journalctl -u cloudflare-tunnel -f
```

#### 3. 認証ループが発生する

**原因**: Google OAuth 設定の問題

**解決方法:**

1. Google Cloud Console でリダイレクト URI 確認
2. Cloudflare Access のアプリケーション設定確認
3. ブラウザ Cookie クリア

#### 4. 一部のサービスにアクセスできない

**原因**: ポート競合またはサービス停止

**解決方法:**

```bash
# ポート確認
netstat -tlnp | grep -E ':(3000|8000|8001)'

# サービス再起動
./scripts/stop-development.sh
./scripts/start-development.sh
```

### デバッグ用コマンド

```bash
# 設定ファイル確認
sudo cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate

# Tunnel 手動実行（デバッグ用）
sudo cloudflared tunnel --config /etc/cloudflared/config.yml run

# ローカルサービス確認
curl -f http://localhost:3000
curl -f http://localhost:8000/health
curl -f http://localhost:8001/health
```

## 📊 監視とメンテナンス

### 定期確認項目

**日次:**

- [ ] Tunnel サービス稼働状態確認
- [ ] 外部アクセス正常性確認

**週次:**

- [ ] アクセスログ確認
- [ ] 異常なアクセスパターンチェック

**月次:**

- [ ] 許可ユーザーリスト見直し
- [ ] セキュリティ設定見直し

### ログ監視

```bash
# Tunnel ログ監視
sudo journalctl -u cloudflare-tunnel -f

# アクセスログ確認（Cloudflare ダッシュボード）
# Analytics > Traffic > Events
```

## 🔒 セキュリティのベストプラクティス

### 推奨設定

1. **認証設定**

   - Google アカウント 2要素認証必須
   - セッション期間: 12-24時間
   - 定期的なアクセス権限見直し

2. **ネットワーク設定**

   - 必要最小限のポート開放
   - Cloudflare Tunnel 使用によるポート開放回避
   - SSL/TLS 暗号化必須

3. **監視・ログ**
   - アクセスログ定期確認
   - 異常なアクセスパターン監視
   - 定期的なセキュリティ監査

### セキュリティチェックリスト

- [ ] 強固なパスワード設定
- [ ] 2要素認証有効化
- [ ] 不要なアクセス権限削除
- [ ] 定期的なアクセスログ確認
- [ ] セキュリティアップデート適用

## 📱 モバイル利用

### 推奨ブラウザ設定

**iOS Safari:**

- JavaScript 有効化
- Cookie 許可
- プライベートブラウジングは無効推奨

**Android Chrome:**

- JavaScript 有効化
- Cookie 許可
- サードパーティ Cookie 許可

### モバイル用 URL ショートカット

ホーム画面にショートカット追加で快適なアクセスが可能:

1. ブラウザで `https://app.yourdomain.com` にアクセス
2. 「ホーム画面に追加」を選択
3. アプリのようにアクセス可能

## 🔄 バックアップと復旧

### 設定バックアップ

```bash
# 重要な設定ファイルをバックアップ
sudo cp /etc/cloudflared/config.yml ~/cloudflare-backup/
sudo cp /etc/cloudflared/coordinate-recorder.json ~/cloudflare-backup/
sudo cp /etc/systemd/system/cloudflare-tunnel.service ~/cloudflare-backup/
```

### 復旧手順

```bash
# 設定復元
sudo cp ~/cloudflare-backup/config.yml /etc/cloudflared/
sudo cp ~/cloudflare-backup/coordinate-recorder.json /etc/cloudflared/
sudo cp ~/cloudflare-backup/cloudflare-tunnel.service /etc/systemd/system/

# サービス再開
sudo systemctl daemon-reload
sudo systemctl enable cloudflare-tunnel
sudo systemctl start cloudflare-tunnel
```

これで外出時でも安全に coordinate-recorder にアクセスできる環境が整います。
