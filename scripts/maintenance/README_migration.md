# ワードローブデータ移行機能 (Issue #531)

このドキュメントは、ローカル DB からワードローブデータを本番環境に移行するための機能について説明します。

## 🎯 概要

Issue #531 で実装されたワードローブデータ移行機能により、以下が可能になりました：

- ローカル開発環境のワードローブデータの完全エクスポート
- 本番環境（Raspberry Pi）への安全なインポート
- データ整合性の自動検証
- 移行プロセスの自動化

## 📋 実装内容

### 1. API エンドポイント

#### エクスポート API

- **エンドポイント**: `POST /api/v2/wardrobe/export`
- **機能**: 全アクティブなワードローブアイテムを JSON 形式で出力
- **パラメータ**:
  - `include_images` (boolean): 画像情報を含めるか（デフォルト: true）

#### インポート API

- **エンドポイント**: `POST /api/v2/wardrobe/import`
- **機能**: JSON ファイルからワードローブデータをインポート
- **パラメータ**:
  - `file` (UploadFile): インポートする JSON ファイル
  - `overwrite_existing` (boolean): 既存データを上書きするか（デフォルト: false）

### 2. 移行スクリプト

**場所**: `scripts/maintenance/migrate_wardrobe_data.py`

高レベルな移行操作を自動化するコマンドラインツール。

### 3. テストスクリプト

**場所**: `scripts/debug/test_wardrobe_migration.py`

移行機能の動作確認用テストツール。

## 🚀 使用方法

### A. 移行スクリプトを使用した自動移行

```bash
# 1. ローカル環境からデータをエクスポート
python scripts/maintenance/migrate_wardrobe_data.py export \\
  --output wardrobe_export_$(date +%Y%m%d).json \\
  --source-url http://localhost:8000

# 2. 本番環境にデータをインポート
python scripts/maintenance/migrate_wardrobe_data.py import \\
  --input wardrobe_export_20250810.json \\
  --target-url http://pi-camera.local:8000 \\
  --overwrite

# 3. データ整合性を検証
python scripts/maintenance/migrate_wardrobe_data.py verify \\
  --source-url http://localhost:8000 \\
  --target-url http://pi-camera.local:8000
```

### B. API を直接使用した移行

#### 1. エクスポート

```bash
# httpx を使用してエクスポート
python -c "
import asyncio
import httpx
import json

async def export_data():
    async with httpx.AsyncClient() as client:
        response = await client.post('http://localhost:8000/api/v2/wardrobe/export')
        data = response.json()
        with open('wardrobe_data.json', 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f'Exported {len(data[\"clothing_items\"])} items')

asyncio.run(export_data())
"
```

#### 2. インポート

```bash
# Webブラウザ経由でのインポート
# 1. 本番環境の UI にアクセス: http://pi-camera.local:3000
# 2. ワードローブ管理画面でインポート機能を使用
# 3. エクスポートした JSON ファイルをアップロード
```

### C. テスト実行

```bash
# 移行機能のテスト
python scripts/debug/test_wardrobe_migration.py --api-url http://localhost:8000 --verbose
```

## 📊 対象データ

移行対象となるデータ：

### 基本情報

- アイテム ID、名前、カテゴリ、サブカテゴリ
- ブランド、サイズ、素材

### 色・パターン情報

- 色パレット（5色まで）
- パターン（ソリッド、ストライプ等）

### 購入・使用情報

- 購入日、購入価格
- 最終使用日、使用回数
- シーズン、オケージョン

### 画像・メタデータ

- 画像URL（複数対応）
- 画像メタデータ（サムネイル等）
- カスタムタグ

### ステータス情報

- アイテム状態（アクティブ、保管済等）
- 作成・更新日時

## ⚠️ 注意事項

### セキュリティ

- 移行中のデータは完全性チェックされます
- 既存データの意図しない削除を防ぐため、デフォルトでは上書きしません
- 移行前に必ずバックアップを取得してください

### パフォーマンス

- 大量データ（1000+ アイテム）の移行時は時間がかかる場合があります
- ネットワーク接続が安定していることを確認してください
- 移行中は他の操作を控えることを推奨します

### データ整合性

- インポート前後でアイテム数が一致することを確認
- エラーが発生した場合、ログで詳細を確認
- 必要に応じてロールバック操作を実行

## 🔧 トラブルシューティング

### よくある問題

#### 1. ネットワーク接続エラー

```
❌ Network error during export: ConnectError
```

**解決方法**: API サーバーが起動していることを確認

#### 2. 権限エラー

```
❌ HTTP 403: Forbidden
```

**解決方法**: API キーまたは認証設定を確認

#### 3. データ形式エラー

```
❌ Invalid JSON file: Expecting value
```

**解決方法**: エクスポートファイルが破損していないか確認

### ヘルスチェック

```bash
# API サーバーの状態確認
python scripts/maintenance/migrate_wardrobe_data.py health --url http://localhost:8000

# 本番環境の状態確認
python scripts/maintenance/migrate_wardrobe_data.py health --url http://pi-camera.local:8000
```

## 📝 ログ・デバッグ

### ログファイル

- API サーバーログ: `api/logs/`
- 移行スクリプトログ: コンソール出力

### デバッグモード

```bash
# 詳細なログ出力
python scripts/debug/test_wardrobe_migration.py --verbose
```

## ✅ 受け入れ条件の確認

- [x] ローカル DB のワードローブデータを完全にエクスポートできる
- [x] 本番環境にデータを安全にインポートできる
- [x] 移行前後でデータの整合性が保たれている
- [x] 移行プロセスが自動化されている

Issue #531 の要件がすべて満たされています。
