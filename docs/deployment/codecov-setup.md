# Codecov セットアップガイド

## 概要

このプロジェクトでは、テストカバレッジの可視化と追跡に [Codecov](https://about.codecov.io/) を使用しています。

## セットアップ手順

### 1. Codecov アカウントの作成

1. [Codecov](https://app.codecov.io/) にアクセス
2. GitHub アカウントでサインイン
3. `unicco/coordinate-recorder` リポジトリを選択

### 2. Upload Token の取得

1. Codecov ダッシュボードでリポジトリを選択
2. Settings → General に移動
3. `CODECOV_TOKEN` をコピー

### 3. GitHub Secrets の設定

1. GitHub リポジトリの Settings → Secrets and variables → Actions
2. "New repository secret" をクリック
3. 以下の情報を入力：
   - Name: `CODECOV_TOKEN`
   - Secret: コピーしたトークン
4. "Add secret" をクリック

### 4. カバレッジの確認

1. テストを含む PR を作成
2. GitHub Actions でテストが実行される
3. Codecov がカバレッジレポートをコメントとして追加
4. README のバッジが自動更新される

## ローカルでのカバレッジ確認

### バックエンド

```bash
# カバレッジレポート生成
pytest --cov=src --cov=api --cov=camera --cov-report=html --cov-report=xml

# HTML レポートを表示
open htmlcov/index.html
```

### フロントエンド

```bash
cd ui

# カバレッジレポート生成
npm run test:unit -- --coverage

# HTML レポートを表示
open coverage/index.html
```

## カバレッジ目標

- **全体**: 70%
- **バックエンド**: 75%
- **フロントエンド**: 60%
- **新規コード**: 80%

詳細な設定は `.github/codecov.yml` を参照してください。
