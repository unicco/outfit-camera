# 共起データ移行手順

## ローカル開発環境でのテスト

### 1. データベースマイグレーション
```bash
cd api
alembic upgrade head
```

### 2. テストデータで移行確認
```bash
# 少量のデータで動作確認
python scripts/migrate_co_occurrence_data.py
```

## 本番環境での初回データ移行

### 1. 本番機にSSH接続
```bash
ssh pi@pi-camera.local
```

### 2. プロジェクトディレクトリに移動
```bash
cd /home/pi/coordinate-recorder
```

### 3. 最新のコードを取得
```bash
git pull origin main
```

### 4. データベースマイグレーション実行
```bash
cd api
source .env  # 本番環境変数読み込み
alembic upgrade head
```

### 5. 既存データの移行実行
```bash
# スクリプトを直接実行
python scripts/migrate_co_occurrence_data.py

# または Python インタープリタで実行（デバッグ時）
python
>>> from app.database import SessionLocal
>>> from app.co_occurrence_batch import CoOccurrenceBatchProcessor
>>> db = SessionLocal()
>>> processor = CoOccurrenceBatchProcessor(db)
>>> processor.migrate_existing_data()
```

### 6. 移行結果の確認
```bash
# PostgreSQL に接続
psql -U coordinate_user -d coordinate_db

-- アイテムペア共起の件数確認
SELECT COUNT(*) FROM item_pair_co_occurrences;

-- カテゴリ共起の件数確認
SELECT COUNT(*) FROM category_co_occurrences;

-- 日次ログの件数確認
SELECT COUNT(*) FROM daily_outfit_logs;
```

## トラブルシューティング

### メモリ不足の場合
```bash
# バッチサイズを小さくして実行
python
>>> processor = CoOccurrenceBatchProcessor(db)
>>> # migrate_existing_data() の中のバッチサイズを調整
>>> # batch_size = 50  # デフォルトは100
```

### エラーが発生した場合
- ログを確認: `tail -f logs/api.log`
- データベース接続を確認: `psql -U coordinate_user -d coordinate_db -c "SELECT 1;"`
- 部分的に移行されたデータはそのまま残るので、再実行しても問題ありません