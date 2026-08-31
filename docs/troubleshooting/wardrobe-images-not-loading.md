# ワードローブ画像表示問題のトラブルシューティング

## 🔍 問題の症状

- ワードローブページで画像が表示されない
- プレースホルダー画像（シャツアイコン）のみが表示される
- ブラウザの開発者ツールで 404 エラーが発生している

## 🚀 クイック診断

### ステップ 1: 診断スクリプトの実行

Raspberry Pi で以下のコマンドを実行して問題を診断：

```bash
cd /home/pi/coordinate-recorder
./scripts/debug/check-wardrobe-images.sh
```

### ステップ 2: サービス状態の確認

```bash
# 全サービスの状態確認
./scripts/health-check.sh quick

# サービス再起動
./scripts/stop-development.sh
./scripts/start-dev.sh
```

### ステップ 3: ブラウザでの確認

1. `http://pi-camera.local:3000` でワードローブページを開く
2. 開発者ツール（F12）を開く
3. **Console タブ**: JavaScript エラーをチェック
4. **Network タブ**: 画像リクエストの応答コードをチェック

## 🔧 詳細診断手順

### API サーバー接続確認

```bash
# ヘルスチェック
curl -f http://pi-camera.local:8000/health

# ワードローブ API 確認
curl -f http://pi-camera.local:8000/api/v2/wardrobe/items
```

### 画像ファイル存在確認

```bash
# ワードローブ画像ディレクトリ確認
ls -la /home/pi/coordinate-recorder/api/v2/wardrobe_images/

# サンプル画像の確認
find /home/pi/coordinate-recorder/api/v2/wardrobe_images/ -name "*.jpg" | head -5
```

### 権限確認

```bash
# ディレクトリ権限確認
ls -ld /home/pi/coordinate-recorder/api/v2/wardrobe_images/

# 権限修正（必要に応じて）
sudo chown -R unicco:unicco /home/pi/coordinate-recorder/api/v2/wardrobe_images/
chmod -R 755 /home/pi/coordinate-recorder/api/v2/wardrobe_images/
```

## 🎯 よくある問題と解決策

### 問題 1: API サーバーが起動していない

**症状**:

- `curl http://pi-camera.local:8000/health` が失敗する
- UI でエラーメッセージが表示される

**解決策**:

```bash
cd /home/pi/coordinate-recorder
./scripts/start-dev.sh
```

### 問題 2: Static Files Mount が機能していない

**症状**:

- API サーバーは起動しているが画像 URL が 404 エラー
- `/static/wardrobe/...` パスにアクセスできない

**解決策**:

1. FastAPI の Static Files Mount 設定を確認
2. `wardrobe_images` ディレクトリが存在するか確認
3. 環境変数 `WARDROBE_IMAGES_DIR` を確認

### 問題 3: 画像ファイルが存在しない

**症状**:

- データベースに URL は保存されているが、ファイルが見つからない
- 個別の画像 URL をテストすると 404 エラー

**解決策**:

1. 画像アップロード機能を再実行
2. バックアップからファイルを復元
3. 画像パスの整合性をチェック

### 問題 4: CORS エラー

**症状**:

- ブラウザの Console で CORS エラーメッセージ
- 同一オリジンからのリクエストも失敗

**解決策**:

1. FastAPI の CORS 設定を確認
2. API サーバーを再起動

## 🖥️ ブラウザでのデバッグ

### Console ログの確認

期待されるログ出力:

```javascript
// 正常な場合
🔍 Fetching wardrobe items from: http://pi-camera.local:8000/api/v2/wardrobe/items
✅ Wardrobe items fetched: [...items...]
🔧 getBestImageUrl called with: {...}
✅ [ItemName] Image loaded successfully

// エラーの場合
❌ [ItemName] Image failed to load: http://pi-camera.local:8000/static/wardrobe/...
🔍 Debug Report for ItemName: {...}
```

### Network タブでの確認

1. ワードローブページを開く
2. **Network タブ**を選択
3. **Images フィルター**を適用
4. 失敗した画像リクエストをクリック
5. **Response**、**Headers**、**Preview** タブを確認

## 📊 詳細デバッグレポート

新しく追加されたデバッグ機能により、画像読み込みエラー時に詳細な診断レポートが Console に出力されます：

```javascript
🔍 Debug Report for ItemName: {
  itemId: "item-id",
  apiUrl: "http://pi-camera.local:8000",
  originalUrls: ["/static/wardrobe/item-id/image-id.jpg"],
  generatedUrls: [
    "http://pi-camera.local:8000/static/wardrobe/item-id/image-id.jpg",
    "http://pi-camera.local:8000/static/wardrobe/item-id/image-id_thumb_200.jpg"
  ],
  testResults: [
    { url: "...", accessible: false, status: 404, error: "HTTP 404: Not Found" }
  ],
  recommendations: [
    "404 エラー: ファイルが見つかりません",
    "1. API サーバーが正常に起動しているか確認",
    "2. Static Files Mount 設定を確認",
    "3. 画像ファイルが実際に存在するか確認"
  ]
}
```

## 🔄 復旧手順

### 完全リセット手順

```bash
cd /home/pi/coordinate-recorder

# 1. すべてのサービスを停止
./scripts/stop-development.sh

# 2. サービスログの確認
ls -la ${PROJECT_ROOT}/logs/

# 3. 権限を修正
sudo chown -R unicco:unicco .
chmod -R 755 .

# 4. サービスを再起動
./scripts/start-dev.sh

# 5. 診断スクリプトで確認
./scripts/debug/check-wardrobe-images.sh
```

### バックアップからの復元

```bash
# ワードローブデータの手動確認
ls -la /home/pi/coordinate-recorder/api/v2/wardrobe_images/
```

## 📞 サポート情報

問題が解決しない場合は、以下の情報を収集してサポートに連絡：

1. 診断スクリプトの出力結果
2. ブラウザの Console ログ
3. ブラウザの Network タブのスクリーンショット
4. サービスの起動状況
5. `/home/pi/coordinate-recorder/api/v2/logs/backend.log` の最新ログ

## 🔄 定期メンテナンス

### 予防的メンテナンス

```bash
# 週次実行推奨
cd /home/pi/coordinate-recorder

# 1. システムヘルスチェック
./scripts/health-check.sh

# 2. ワードローブ画像診断
./scripts/debug/check-wardrobe-images.sh

# 3. サービス状態確認
./scripts/monitor-services.sh status
```
