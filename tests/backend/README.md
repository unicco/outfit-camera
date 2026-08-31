# テストガイド

このディレクトリには、Coordinate Recorder Manager プロジェクトのすべてのテストが含まれています。

## テスト構造

```
tests/
├── backend/              # バックエンド (Python) テスト
│   ├── unit/            # ユニットテスト
│   ├── integration/     # 統合テスト（API、DB、外部サービス）
│   └── performance/     # パフォーマンステスト
├── frontend/            # フロントエンド (React/TypeScript) テスト
│   ├── unit/           # コンポーネントユニットテスト
│   └── integration/    # UI 統合テスト
├── e2e/                # End-to-End テスト (Playwright)
├── fixtures/           # テストデータ・モック
└── issues/             # Issue 固有のテスト

scripts/
├── debug/              # デバッグ用スクリプト（旧 tests/debug）
└── demo/               # デモ用スクリプト（旧 tests/demo）
```

## テスト実行方法

### バックエンドテスト

```bash
# すべてのバックエンドテスト
pytest tests/backend/

# ユニットテストのみ
pytest tests/backend/unit/

# 統合テストのみ
pytest tests/backend/integration/

# パフォーマンステストのみ
pytest tests/backend/performance/

# カバレッジレポート付き
pytest --cov=src --cov=api --cov=camera --cov-report=html

# 特定のマーカーでフィルタ
pytest -m "not slow"      # 遅いテストを除外
pytest -m unit           # ユニットテストのみ
pytest -m integration    # 統合テストのみ
```

### フロントエンドテスト

```bash
cd ui

# ユニットテスト
npm run test:unit

# 統合テスト
npm run test:integration

# ウォッチモード
npm run test:unit:watch

# すべてのテスト
npm run test
```

### E2E テスト

```bash
cd ui

# E2E テスト実行
npm run test:e2e

# ヘッドレスモード
npm run test:e2e:headless

# 特定のテストファイル
npx playwright test tests/e2e/test-touchscreen-verification.spec.js
```

## テスト環境設定

### 必要な環境変数

統合テストを実行する前に、以下の環境変数を設定してください：

```bash
# データベース接続
export DATABASE_URL="postgresql+psycopg://coordinate_user:coordinate_pass@localhost:5438/coordinate_test_db"

# API キー（必要に応じて）
export JINA_API_KEY="your_test_api_key"

# テストモード
export TEST_MODE=true
```

### データベースセットアップ

統合テストにはテスト用データベースが必要です：

```bash
# PostgreSQL サーバー起動（開発環境）
./scripts/start-development.sh  # PostgreSQL も同時に起動

# テストデータベース作成
createdb coordinate_test_db
```

## CI/CD 統合

GitHub Actions で自動的にテストが実行されます：

- **プッシュ時**: ユニットテストと軽量な統合テスト
- **PR 作成時**: フルテストスイート（E2E を含む）
- **main ブランチ**: パフォーマンステストも実行

ワークフロー: `.github/workflows/test.yml`

### 段階的有効化計画

現在、CI/CD ワークフローは `workflow_dispatch`（手動実行）のみ有効です。以下の段階で有効化予定：

1. **Phase 1**: バックエンドユニットテストのみ push 時に有効化
2. **Phase 2**: 統合テストを追加（データベース接続が必要）
3. **Phase 3**: E2E テストを追加（フロントエンドビルドが必要）
4. **Phase 4**: パフォーマンステストを main ブランチで有効化

## テスト作成ガイドライン

### ユニットテスト

- 外部依存関係をモック化
- 1つの機能に焦点を当てる
- 高速実行（< 1秒）
- ファイル名: `test_*.py`

### 統合テスト

- 実際のデータベース/サービスを使用
- 複数のコンポーネントの連携をテスト
- `@pytest.mark.integration` デコレータを使用
- 遅いテストには `@pytest.mark.slow` を追加

### パフォーマンステスト

- 処理時間、メモリ使用量を測定
- ベンチマークとの比較
- `@pytest.mark.performance` デコレータを使用

### E2E テスト

- ユーザーシナリオを再現
- 実際のブラウザで実行
- スクリーンショット付きレポート

## 特殊なテストディレクトリ

### performance/ - AI パフォーマンステスト

- `test_ai_detection.py` - AI 衣類検出機能の基本テスト
- `test_fullbody_vs_crop.py` - 全身写真 vs クロップ画像精度比較
- `test_color_analysis_methods.py` - 色抽出手法比較
- `test_crop_implementation.py` - クロップ画像実装効果テスト
- `test_task_optimization.py` - Jina API タスク最適化テスト

### issues/ - Issue 固有のテスト

- `test_issue_233_implementation.py` - Issue #233 実装テスト
- `test_issue_237.py` - Issue #237 データベース統一テスト

## デバッグツール

デバッグ用スクリプトは `scripts/debug/` に移動されました：

```bash
# 色分析デバッグ
python scripts/debug/debug_similarity_ranking.py

# API デバッグ
python scripts/debug/test_outfit_api_debug.py

# 埋め込みフィルタリング調査
python scripts/debug/debug_embedding_filter.py
```

## デモスクリプト

デモ用スクリプトは `scripts/demo/` に移動されました：

```bash
# ワードローブ AI 分析デモ
python scripts/demo/demo_wardrobe_ai_analysis.py

# カスタマイズ可能な色サンプリング
python scripts/demo/demo_customizable_color_sampling.py
```

## トラブルシューティング

### モジュールが見つからない

```bash
# PYTHONPATH を設定
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/src:$(pwd)/api"
```

### データベース接続エラー

```bash
# PostgreSQL が起動しているか確認
ps aux | grep postgres

# データベースを再作成
dropdb coordinate_test_db
createdb coordinate_test_db
```

### Playwright エラー

```bash
# ブラウザを再インストール
npx playwright install --with-deps chromium
```

## テスト実行順序（CI/CD）

1. **Unit Tests** - 高速フィードバック
2. **Performance Tests** - AI 機能品質確認
3. **Integration Tests** - サービス品質確認
4. **E2E Tests** - 最終品質保証

テスト失敗時は早期に CI を停止し、開発効率を向上させます。
