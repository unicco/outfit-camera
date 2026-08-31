# GitHub Actions 削除済ワークフローのクリーンアップガイド

## 問題の概要

GitHub では、`.github/workflows/` ディレクトリからワークフローファイルを削除しても、GitHub Actions の UI に古いワークフローが残り続けることがあります。これは GitHub の仕様によるもので、以下の理由があります：

1. **履歴保持**: 過去の実行履歴を保持するため
2. **監査目的**: セキュリティとコンプライアンスのため
3. **キャッシュ**: UI のパフォーマンス最適化のため

## 現在の状況（2025年8月時点）

以下のワークフローがファイルは削除されているが、GitHub UI に残存している：

- CI/CD Pipeline
- Dependabot Updates
- API Endpoint Tests (Smart)
- Smart Testing - Run Only Relevant Tests
- Systemd Validation

## クリーンアップ方法

### 方法1: GitHub CLI を使用した確認

```bash
# 現在のワークフロー一覧を取得
gh workflow list

# 特定のワークフローの詳細を確認
gh workflow view "ワークフロー名"

# 削除されたワークフローの実行履歴を確認
gh run list --workflow="削除されたワークフロー名" --limit=5
```

### 方法2: ワークフローの無効化

削除済ワークフローは API 経由で無効化できる場合があります：

```bash
# ワークフローIDを取得
workflow_id=$(gh api repos/:owner/:repo/actions/workflows | jq -r '.workflows[] | select(.name=="ワークフロー名") | .id')

# ワークフローを無効化
gh api -X PUT repos/:owner/:repo/actions/workflows/$workflow_id/disable
```

### 方法3: 実行履歴の削除

古い実行履歴を削除することで、UI から消える場合があります：

```bash
# 特定ワークフローの古い実行を削除
gh run list --workflow="ワークフロー名" --limit=100 --json databaseId -q '.[].databaseId' | \
while read run_id; do
  echo "Deleting run $run_id"
  gh api -X DELETE repos/:owner/:repo/actions/runs/$run_id
done
```

### 方法4: GitHub サポートへの連絡

上記の方法で解決しない場合は、GitHub サポートに連絡することを推奨します：

1. https://support.github.com/ にアクセス
2. "Contact Support" を選択
3. 以下の情報を提供：
   - リポジトリ名
   - 削除したいワークフロー名のリスト
   - ワークフローファイルを削除した日時
   - 試した対処法

## 予防策

### 1. ワークフローの適切な廃止手順

```yaml
name: 🚫 [DEPRECATED] Old Workflow

# このワークフローは削除予定です
# 削除予定日: YYYY-MM-DD
# 移行先: new-workflow.yml

on:
  workflow_dispatch: # 手動実行のみに制限

jobs:
  deprecated:
    runs-on: ubuntu-latest
    steps:
      - name: ⚠️ Deprecation Notice
        run: |
          echo "::warning::This workflow is deprecated and will be removed on YYYY-MM-DD"
          echo "Please use new-workflow.yml instead"
          exit 1  # 実行を失敗させる
```

### 2. 段階的な削除プロセス

1. **Stage 1**: ワークフローを無効化（上記の例）
2. **Stage 2**: 1-2週間後、実行履歴を確認
3. **Stage 3**: 実行がないことを確認してファイル削除
4. **Stage 4**: 必要に応じて実行履歴も削除

### 3. ワークフロー管理のベストプラクティス

- 不要になったワークフローは即座に削除せず、まず無効化
- 削除前に実行履歴の必要性を確認
- 重要なワークフローは削除前にバックアップ
- チーム内で削除の影響を事前に共有

## トラブルシューティング

### Q: ワークフローが UI から消えない

A: 以下を順番に試してください：

1. ブラウザのキャッシュをクリア
2. 別のブラウザでアクセス
3. 24-48時間待つ（GitHub のキャッシュ更新）
4. GitHub サポートに連絡

### Q: 削除したワークフローが実行されている

A: 以下を確認してください：

1. 別のブランチにワークフローファイルが残っていないか
2. フォークされたリポジトリで実行されていないか
3. スケジュール実行がキューに残っていないか

### Q: ワークフロー ID が見つからない

A: GraphQL API を使用して詳細情報を取得：

```bash
gh api graphql -f query='
{
  repository(owner: "OWNER", name: "REPO") {
    workflows(first: 100) {
      nodes {
        name
        databaseId
        resourcePath
        state
      }
    }
  }
}'
```

## 参考リンク

- [GitHub Actions ワークフローの無効化と有効化](https://docs.github.com/en/actions/managing-workflow-runs/disabling-and-enabling-a-workflow)
- [GitHub Actions の使用量制限](https://docs.github.com/en/actions/learn-github-actions/usage-limits-billing-and-administration)
- [GitHub CLI workflows コマンド](https://cli.github.com/manual/gh_workflow)

## まとめ

削除済ワークフローの表示は GitHub の仕様上完全に防ぐことは困難ですが、適切な管理と段階的な削除プロセスにより、混乱を最小限に抑えることができます。どうしても削除が必要な場合は、GitHub サポートへの連絡が最も確実な方法です。
