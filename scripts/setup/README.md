# Setup Scripts

このディレクトリには、Coordinate Recorder の初期セットアップ、環境構築、サービス設定に関するスクリプトが含まれています。

## 🆕 新規追加スクリプト (Issue #886 対応)

### setup-venv-deployment.sh

Raspberry Pi での `externally-managed-environment` エラーを解決し、仮想環境の管理とデプロイメントを支援します。

**主な機能:**

- 仮想環境の自動作成・検出・アクティベート
- 依存関係の自動インストール (requirements.txt, Google Photos API など)
- systemd サービスの自動更新
- ヘルスチェック統合
- バックアップ機能

**使用方法:**

```bash
# 通常の実行（仮想環境作成と依存関係インストール）
./setup-venv-deployment.sh

# 確認なしで実行
./setup-venv-deployment.sh --force

# ヘルスチェックのみ
./setup-venv-deployment.sh --check-only

# サービス再起動のみ
./setup-venv-deployment.sh --restart-only

# 依存関係の更新のみ
./setup-venv-deployment.sh --update-deps
```

**externally-managed-environment エラーが発生した場合:**

```bash
# このエラーを解決するために実行
./setup-venv-deployment.sh
```

### update-systemd-services.sh

systemd サービスファイルの仮想環境パスを自動的に更新します。

**主な機能:**

- 仮想環境パスの自動検出と更新
- coordinate-api.service と coordinate-camera.service の設定更新
- ドライランモード対応
- サービスファイルのバックアップ

**使用方法:**

```bash
# 通常の実行
./update-systemd-services.sh

# ドライラン（実際の変更なし）
./update-systemd-services.sh --dry-run
```

## 監視・サービス設定

### カメラ監視サービス設定

カメラサービスの自動監視・復旧システムをsystemdサービスとして登録します。

#### 使用方法

```bash
# 監視サービスをインストール
sudo ./scripts/setup/install-watchdog-service.sh

# サービス状態確認
sudo systemctl status coordinate-camera-watchdog

# ログ確認
sudo journalctl -u coordinate-camera-watchdog -f
```

#### 機能

- **30秒間隔監視**: カメラサービスの健全性を定期チェック
- **自動復旧**: 3回連続失敗で自動再起動
- **Discord通知**: 復旧成功・失敗をDiscordに通知
- **リソース制限**: メモリ100MB、CPU 10%制限
- **環境別最適化**: Raspberry Pi(300MB) vs 開発環境(500MB)のメモリ閾値自動調整
- **セキュア設計**: sudo使用を最小限に制限、代替手段を優先使用

## セキュリティ設定

### sudoers は生成しない

**このディレクトリに sudoers を書くスクリプトは無い。** 玄関 Pi の `unicco` は `/etc/sudoers.d/010_pi-nopasswd`（Raspberry Pi OS 標準）で `NOPASSWD: ALL` を持つため、細かい許可ファイルは既に許可済の部分集合でしかなかった。狭めない判断とその前提は [`deploy/docs/pi-sudo-policy.md`](../../deploy/docs/pi-sudo-policy.md)。

削除した 3 本。

- `setup-sudoers.sh`（`/etc/sudoers.d/kiosk-display-control` を毎起動生成）— `/bin/sh -c` にワイルドカードを付ける形で、最小権限として機能していなかった
- `sudoers-watchdog`（`fuser -k 8001/tcp` を許可するテンプレート）— インストーラが存在せず、実機の同名ファイルとも中身が違う孤児だった
- `configure-sudoers.sh`（`/etc/sudoers.d/coordinate-recorder-backlight` を書く）— 生成物が本番 Pi に存在せず、一度も適用されていなかった

実機に残っていた `kiosk-display-control` / `coordinate-display` / `coordinate-recorder-watchdog` は、`deploy/setup-pi.sh` の `OBSOLETE_SUDOERS` が毎起動で削除する。
