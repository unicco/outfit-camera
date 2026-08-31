# ローカル品質チェックガイド

CI の "Fast Quality Checks" と同じコマンドセットをローカルで再現するためのガイドです。コミット前に以下のコマンドを実行し、Ruff や Black、npm lint の失敗を防止してください。

## 前提: 品質ツールを `.venv` に入れる

`run-checks.sh` は `ruff` / `black` / `mypy` / `pytest` を呼びます。**素の clone 直後の `.venv` には入っていません。**入れずに実行すると最初の Ruff で止まります。

```bash
.venv/bin/pip install -r requirements-dev.txt
```

## ワンコマンドで実行する

```bash
npm run checks
```

- `./scripts/dev/run-checks.sh` を実行し、Python と UI のチェックをまとめて走らせます。
- エラーが発生した場合は対象コマンドと再実行方法が表示されます。

### 変更差分だけチェックする

```bash
npm run checks:auto
```

- `--auto-scope` オプションが有効になり、`origin/main`（または `main`）との差分から Python/UI チェックを自動判定します。
- UI チェックが必要な場合は差分のベースコミットを `Vitest` の `--changed` 比較対象として自動設定します。
- 対象となる変更が無い場合はスキップされます。
- 比較元を指定したいときは以下のように指定してください：

```bash
bash scripts/dev/run-checks.sh --auto-scope --base upstream/main
```

## スクリプトを直接操作する

```bash
# すべてのチェックを実行
bash scripts/dev/run-checks.sh

# UI チェックをスキップ
RUN_UI_CHECKS=0 bash scripts/dev/run-checks.sh

# Vitest の比較対象を手動指定
VITEST_CHANGED_SINCE=origin/main bash scripts/dev/run-checks.sh
```

環境変数やオプションの詳細は `bash scripts/dev/run-checks.sh --help` で確認できます。

### 部分的に実行したい場合

- DB をローカルで起動できない場合: `SKIP_DB_TESTS=1 npm run checks`（Pytest のみスキップし、それ以外のチェックは実行されます）
- Python だけ / UI だけに絞る場合: `RUN_UI_CHECKS=0 npm run checks` / `RUN_PYTHON_CHECKS=0 npm run checks`

> ℹ️ データベースが未起動でも、スクリプトはデフォルトで `.tmp/run-checks/pytest.db` の SQLite を使用します。どうしても Pytest を実行できない場合のみ `SKIP_DB_TESTS=1` を利用してください。

## Git hooks

コミット時に gitleaks が staged 差分を秘密情報スキャンします。clone 後に一度だけ有効化してください。

```bash
git config core.hooksPath .githooks
```

- 誤検知だと確認できた場合のみ `GITLEAKS_SKIP=1 git commit ...` でバイパスします
- gitleaks 未インストールならスキャンはスキップされます（`brew install gitleaks`）

`ruff` / `black` / `mypy` を push 時に自動実行するフックは**置いていません**。同じ検査は CI の "Fast Quality Checks" が required で実行するので、手元では上記の `npm run checks` を明示的に叩いてください。

## よくあるエラーの対処

- **Ruff や Black が失敗する場合**: `ruff --fix` や `black` を該当ディレクトリに対して手動で実行し、変更をコミットしてください。
- **npm lint が失敗する場合**: `npm --prefix ui run lint` で詳細を確認し、ESLint の指示に従って修正します。
- **Vitest で差分対象が見つからない場合**: `git fetch origin` を実行した上で `--base` オプションを指定するか、`VITEST_CHANGED_SINCE` を直接設定してください。
