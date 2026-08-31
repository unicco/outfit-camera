# データベースセットアップ手順

本プロジェクトのデータベースは Alembic により管理します。2025-10-04 以降は `api/alembic/versions/0001_initial.py` がベースリビジョンとなり、初期構築や再構築は以下の手順を利用してください。

## 新規セットアップ（ローカル・検証環境）

```bash
# 任意の検証用データベースを作成
createdb coordinate_db_schema_test

# Alembic を実行
cd api
DATABASE_URL=postgresql+psycopg://coordinate_user:coordinate_pass@localhost:5432/coordinate_db_schema_test \
  ./venv/bin/alembic -c alembic.ini upgrade head
```

実行後、`alembic_version` には `0001_initial` のみが記録され、スキーマは本番と同一状態になります。

## 既存環境の切り替え（ローカル / 本番）

既存データベースには旧マイグレーションの履歴が残っています。今後は新しいベースリビジョンを利用するため、以下の順で整合性を取ります。

1. **バックアップ**を取得（例: `pg_dump -Fc`）。本番機では `/home/pi/backups/coordinate_db_YYYYMMDD.dump` などに保存してください。
2. Alembic のバージョン管理を新ベースに合わせる：
   ```bash
   cd api
   DATABASE_URL=postgresql+psycopg://<user>:<pass>@<host>:5432/<dbname> \
     ./venv/bin/alembic -c alembic.ini stamp 0001_initial
   ```
   既存スキーマはそのまま、新しいバージョン番号だけが記録されます。
3. 必要に応じて `alembic upgrade head` を実行（`head` = `0001_initial` のため実行しても変更はありませんが、差分チェックとして有効です）。

## 運用上の注意

- `coordinate_user` には `CREATEDB` 権限を付与済です。検証用データベースは自身で作成できます。
- 旧リビジョンファイルは削除済です。手元に残っている作業ディレクトリがあれば `git pull` 後に `alembic/versions` が `0001_initial.py` のみに更新されていることを確認してください。
- 追加の構造変更が必要な場合は、`0001_initial` を基準に通常どおり新しいリビジョンを作成してください。

## 本番適用時のチェックリスト

- バックアップファイルが最新か確認（例: `tg --list /home/pi/backups`）。
- `alembic stamp 0001_initial` を実行し、`SELECT version_num FROM alembic_version;` が `0001_initial` になっているか確認。
- アプリケーションを再起動（必要に応じて `systemctl restart coordinate-*`）。

以上で、新しいベースマイグレーションに完全移行できます。

## 本番の DB 認証情報

- `DATABASE_URL` の `coordinate_pass` は**ローカル開発用のデフォルト値**。本番では必ず強固なパスワードへ rotate する（生成例: `openssl rand -hex 24`）。
- 本番 `.env` に `REQUIRE_SECURE_DB_CREDENTIALS=true` を設定すると、`DATABASE_URL` にデフォルト値 `coordinate_pass` が含まれる場合に**起動を失敗させる**（`app.settings` のバリデーション）。デフォルト認証情報のまま本番が黙って起動する事故を防ぐ。
- `ENVIRONMENT=production` ではなく専用フラグで判定する理由: `ENVIRONMENT=production` は `auth.py` / `security.py` の厳格認証も同時に有効化してしまうため。
