# 共有仮想環境 (venv) 管理ガイド

このドキュメントは、coordinate-recorder プロジェクトにおける効率的な仮想環境管理について説明します。

## 概要

このプロジェクトでは、**共有仮想環境**の仕組みを採用しています。requirements ファイルのハッシュに基づいて venv を作成・再利用することで、効率的な依存関係管理を実現します。

## 仕組み

1. **共有ディレクトリ**: 仮想環境はリポジトリの `.venvs/` に保存されます

   ```
   /Users/unicco/repos/coordinate-recorder/.venvs/
   ├── api-server-{hash}/
   ├── camera-server-{hash}/
   └── ui-server-{hash}/
   ```

2. **ハッシュベース管理**: requirements ファイルのハッシュに基づいて venv を作成・再利用

3. **シンボリックリンク**: 各サービスの `venv` は共有 venv へのシンボリックリンク

4. **最終使用の記録**: 起動のたびに、選んだ世代を `touch` して mtime を更新する。
   venv への書き込みは `site-packages` 配下に入りディレクトリ自身の mtime を動かさないため、
   touch しないと mtime が作成日時のまま固定され、毎日使っている世代と放置された世代を
   区別できない。旧世代の回収（下記）はこの mtime を「最終使用」として読む

## 旧世代の回収

requirements を更新するとハッシュが変わって新しい venv が作られるが、**旧世代は誰も消さない**。
2026-08 の実測で `.venvs/` に 3.6GB、`~/.coordinate-recorder-venvs/` に 2.6GB が積み上がっていた
（全世代が torch 385MB を抱えたまま。torch は依存から外れて久しい）。

```bash
# 候補の一覧だけ（既定・何も消さない）
bash scripts/maintenance/prune-stale-venvs.sh

# 実際に削除する
bash scripts/maintenance/prune-stale-venvs.sh --apply

# 猶予日数を変える（既定 30 日）
bash scripts/maintenance/prune-stale-venvs.sh --days 60
```

現在のチェックアウトの `api/venv`・`camera/venv` が指す世代は、古くても消さない。

### なぜ起動時に自動でやらないか

判定材料が mtime しかなく、**猶予を超えて起動したまま動いているサービスの venv と、
放置された venv を区別できない**。デプロイのたびに自動で走らせると、稼働中プロセスが
使っている世代を消して symlink を宙づりにする。遅延 import や subprocess の起動で落ちる。

そのため回収は人間が明示的に叩くコマンドにしてある。猶予を超えて再起動していない
サービスがあるなら、`--apply` の後にそのサービスを再起動すること。

   > この回収を入れる前は旧世代が永久に残り、ローカル実測で `.venvs/` に 3.6GB、
   > `~/.coordinate-recorder-venvs/` に 2.6GB の死んだ世代が積み上がっていた。

## セットアップ

### 開発環境の起動

```bash
./scripts/start-development.sh
```
初回実行時に自動的に共有 venv が作成されます。

### 手動でのセットアップが必要な場合

```bash
cd api
source ../scripts/launch/common/python-setup.sh
setup_python_env "API Server" "$(pwd)" "../requirements-api.txt"
```

## トラブルシューティング

### 問題: 新しいパッケージがインストールされない

**原因**: requirements ファイルを更新したが、古い venv を参照している

**解決方法**:

```bash
# 1. 既存のシンボリックリンクを削除
cd api && rm -f venv

# 2. セットアップを再実行
./scripts/start-development.sh
```

### 問題: 共有 venv が壊れた

**解決方法**:

```bash
# 1. 壊れた venv を削除
rm -rf .venvs/api-server-*

# 2. 再作成
cd api
source ../scripts/launch/common/python-setup.sh
setup_python_env "API Server" "$(pwd)" "../requirements-api.txt"
```

### 問題: 異なるバージョンの Python を使いたい

**解決方法**: pyenv で Python バージョンを切り替えてから venv を再作成

```bash
pyenv local 3.12.8
# その後、上記の手順で venv を再作成
```

## ベストプラクティス

1. **requirements を変更したら**:

   - requirements ファイルを更新後は必ず `start-development.sh` を再実行
   - これにより新しいハッシュで venv が作成される

2. **パッケージの追加インストール**:

   ```bash
   # 共有 venv に直接インストール
   cd api
   ./venv/bin/pip install package-name
   ```

   動作を確認したら `requirements-api.txt` に **1 行を手で足す**（`package-name==X.Y.Z`）。
   版の決め方は同ファイル冒頭のコメントに従う。

   > [!WARNING]
   > **`pip freeze` の出力を `requirements-api.txt` に流し込まないこと。**
   > このファイルは `deploy/setup-vps.sh` が読むので、書いた内容がそのまま本番 VPS に入る。
   > 上書きすると (1) ピンの根拠コメント（どの CVE でその版を選んだか・なぜ推移的依存の
   > `starlette` / `packaging` / `scipy` を直接書いているか）が全部消える、(2) 直接依存だけの
   > ファイルが推移的依存込みの lock ファイルに化ける、(3) ローカルの OS / Python 版で
   > 解決された結果が本番に流れる。`packaging` を落とすと本番の venv drift 検査
   > （`scripts/maintenance/check_venv_drift.py`）が動かなくなる。

3. **CI/CD での利用**:
   - GitHub Actions でも同様の共有 venv の仕組みを使用可能
   - キャッシュキーに requirements のハッシュを使用

## メリット

1. **時間短縮**: 既存の venv を再利用
2. **ディスク容量節約**: 重複した venv を作らない
3. **一貫性**: 同じ requirements なら同じ環境を保証

## 注意事項

- Python バージョンを変更した場合は venv の再作成が必要
- プロダクション環境では別の venv 管理を使用
