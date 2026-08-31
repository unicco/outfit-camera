# 開発スクリプトから systemd への移行ガイド

## ⚠️ 重要なお知らせ

このディレクトリ内のスクリプト（`start-development.sh`、`stop-development.sh`）は**将来的に廃止予定**です。
今後は systemd を使用した管理に移行してください。

## 移行の理由

1. **安定性の向上**: systemd による自動再起動とプロセス管理
2. **ログ管理**: journalctl による統一的なログ管理
3. **本番環境との一貫性**: 開発環境と本番環境で同じ管理方法
4. **リソース管理**: メモリやCPU制限の適切な設定

## コード検証の統合チェック

日々の検証は `./scripts/dev/run-checks.sh` で一括実行できます。Ruff、Black、MyPy、pytest、UI の lint と型チェックを順番に呼び出し、失敗するとその場で止まります。PR を作成する前に必ずこのスクリプトを実行し、結果を PR テンプレートに記載してください。

```bash
./scripts/dev/run-checks.sh
```

失敗時は該当コマンドと再実行方法を表示するので、指示に従って個別に修正してから再度スクリプトを実行してください。CI では `ci-lint-check` ワークフローが同じ `run-checks.sh` を実行し、重いテストは手動トリガー運用としています。

重い統合テストや E2E テストが必要な場合は GitHub Actions の `Test Suite` ワークフローを手動実行するか、PR に `ci:e2e` ラベルを付与してキックしてください（デフォルトでは自動実行されません）。

## 移行方法

### 従来の方法（廃止予定）

```bash
# 起動
./scripts/dev/start-development.sh

# 停止
./scripts/dev/stop-development.sh
```

### 新しい方法（推奨）

```bash
# 起動
./systemd/scripts/start-services.sh
# または
sudo systemctl start coordinate-*.service

# 停止
./systemd/scripts/stop-services.sh
# または
sudo systemctl stop coordinate-*.service

# 状態確認
./systemd/scripts/status-services.sh
# または
sudo systemctl status coordinate-*.service
```

## 開発環境での systemd 使用

### Linux（Ubuntu、Debian、Raspberry Pi OS）

systemd がデフォルトで利用可能です。上記のコマンドをそのまま使用できます。

### macOS

macOS では systemd が利用できないため、当面は開発スクリプトを使用してください。
ただし、以下の代替案を検討してください：

1. Python 仮想環境での直接実行
2. Linux VM での開発
3. リモート開発環境の使用

### Windows (WSL2)

WSL2 では systemd がサポートされています。以下の設定を有効にしてください：

```ini
# /etc/wsl.conf
[boot]
systemd=true
```

## 個別サービスの管理

### カメラサービスのみ

```bash
# 起動
sudo systemctl start coordinate-camera.service

# ログ確認
sudo journalctl -u coordinate-camera -f
```

### API サービスのみ

```bash
# 起動
sudo systemctl start coordinate-api.service

# ログ確認
sudo journalctl -u coordinate-api -f
```

### UI サービスのみ

```bash
# 起動
sudo systemctl start coordinate-ui.service

# ログ確認
sudo journalctl -u coordinate-ui -f
```

## トラブルシューティング

### サービスが起動しない場合

```bash
# エラーログの確認
sudo journalctl -u coordinate-camera.service -n 50

# サービスファイルの再読み込み
sudo systemctl daemon-reload

# サービスのリセット
sudo systemctl reset-failed coordinate-*.service
```

### ポート競合の場合

```bash
# 使用中のポートを確認
sudo lsof -i :8000  # API
sudo lsof -i :8001  # Camera
sudo lsof -i :3000  # UI
```

## 移行スケジュール

- **現在**: 両方の方法が利用可能（systemd 推奨）
- **2025年Q2**: 開発スクリプトのメンテナンス終了
- **2025年Q3**: 開発スクリプトの削除

## 質問・サポート

移行に関する質問は、GitHub Issues で受け付けています。
