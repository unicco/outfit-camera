# Google Photos OAuth セキュリティ考慮事項

このドキュメントでは、Google Photos OAuth 統合におけるセキュリティの考慮事項と今後の改善提案について説明します。

## 現在の実装

### nginx プロキシ設定

- Google Photos OAuth コールバック (`/oauth2callback`) と API エンドポイント (`/google-photos/`) をプロキシ
- 適切なヘッダー転送（`X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`）
- タイムアウト設定（60秒）で長時間処理に対応
- 大きな画像ファイルのアップロードに対応するバッファ設定

## セキュリティ上の考慮事項

### 1. CSRF (Cross-Site Request Forgery) 対策

**現状**: OAuth フローにおける state パラメータの検証は FastAPI バックエンドで実装されています。

**推奨事項**:

- バックエンドでの state パラメータ検証の継続的な監視
- セッション固有のランダムな state 値の使用
- state 値の有効期限設定（推奨: 10分）

### 2. Referer チェック

**現状**: nginx レベルでの Referer チェックは実装されていません。

**将来の改善案**:

```nginx
# OAuth コールバックに Referer チェックを追加する例
location /oauth2callback {
    # Google からのリダイレクトのみ許可
    valid_referers none blocked accounts.google.com *.google.com;
    if ($invalid_referer) {
        return 403;
    }
    # 既存のプロキシ設定...
}
```

### 3. Content Security Policy (CSP)

**現状**:

- 現在の CSP: `img-src * data: blob:` （非常に緩い設定）

**推奨事項**:

```nginx
# より厳格な CSP の例
add_header Content-Security-Policy "
    default-src 'self';
    script-src 'self';
    style-src 'self' 'unsafe-inline';
    img-src 'self' data: blob: https://*.googleusercontent.com https://lh3.googleusercontent.com;
    connect-src 'self' https://photoslibrary.googleapis.com;
" always;
```

### 4. レート制限

**現状**: nginx レベルでのレート制限は未実装。

**将来の改善案**:

```nginx
# レート制限の設定例
limit_req_zone $binary_remote_addr zone=oauth_limit:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;

location /oauth2callback {
    limit_req zone=oauth_limit burst=5 nodelay;
    # 既存の設定...
}

location /google-photos/ {
    limit_req zone=api_limit burst=20 nodelay;
    # 既存の設定...
}
```

## 実装優先度

1. **高優先度**:

   - バックエンドでの state パラメータ検証の確認と強化
   - CSP ヘッダーの Google Photos ドメイン明示

2. **中優先度**:

   - レート制限の実装
   - アクセスログの監視強化

3. **低優先度**:
   - Referer チェックの追加（Google OAuth の仕様変更に影響される可能性があるため）

## 監視とログ

### 推奨されるログ監視項目

- OAuth コールバックへの異常なアクセスパターン
- 短時間での大量の API リクエスト
- 認証失敗の頻度
- 大きなファイルアップロードの頻度と成功率

## まとめ

現在の実装は基本的なセキュリティ要件を満たしていますが、本番環境での長期運用を考慮すると、上記の改善項目を段階的に実装することを推奨します。特に、state パラメータの適切な検証とCSP の強化は早期に対応すべき項目です。
