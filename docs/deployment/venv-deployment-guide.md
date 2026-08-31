# 仮想環境デプロイメントガイド

> [!WARNING]
> **このガイドは現行のデプロイ方式と一致しない**（2026-07-27 確認）。読む前に以下を把握すること。
>
> - 記載の `api/requirements.txt` は**存在しない**（ルートの `requirements-api.txt` に統合済）
> - 「常に仮想環境を使用」とあるが、**Pi の camera は `/usr/bin/python3`（システム Python）で動く**（`coordinate-camera.service` の ExecStart）。Picamera2 がシステムレベルでのみ利用可能なため
> - 本文が作成を勧める `~/coordinate-recorder/venv` は、現行の `deploy/setup-pi.sh` が「旧 API 用 venv」として**削除する**
> - 呼び出しの起点である `scripts/setup/setup-venv-deployment.sh` は、現行の CI/CD デプロイ（`.github/workflows/deploy-raspberry-pi.yml`）からは呼ばれていない
>
> 現行の正: **VPS の API** = `deploy/setup-vps.sh` が `.venv` に `requirements-api.txt` を入れる／**Pi の camera** = システム Python + apt + `~/.local`（宣言されていない。 で扱う）。
> 依存の版方針は `requirements-api.txt` 冒頭のコメントを参照。

このガイドでは、Raspberry Pi での `externally-managed-environment` エラーを解決し、Python 仮想環境を使用したデプロイメント方法について説明します。

## 背景

Raspberry Pi OS Bookworm 以降では、システム Python パッケージへの直接インストールが制限されており、以下のようなエラーが発生します：

```
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
    python3-xyz, where xyz is the package you are trying to
    install.
```

## 解決方法

### 1. setup-venv-deployment.sh の使用

専用のセットアップスクリプトを使用することで、仮想環境の作成から依存関係のインストール、サービスの設定まで自動化できます。

```bash
cd ~/coordinate-recorder
./scripts/setup/setup-venv-deployment.sh
```

### 2. スクリプトの機能

#### 仮想環境管理

- 仮想環境の自動作成（`~/coordinate-recorder/venv`）
- 既存環境の検出と再利用
- pip のアップグレード

#### 依存関係管理

- `api/requirements.txt` の自動インストール
- `camera/requirements.txt` の自動インストール
- Google Photos API パッケージの追加インストール
- 新しいパッケージの自動検出

#### systemd サービス管理

- 仮想環境パスの自動更新
- サービスファイルのバックアップ
- サービスの再起動

#### ヘルスチェック

- API サーバーの動作確認
- Camera サーバーの動作確認
- Python httpx を使用した HTTP チェック

## 使用例

### 通常のデプロイメント

```bash
# 仮想環境作成と依存関係インストール
./scripts/setup/setup-venv-deployment.sh
```

### オプションの使用

```bash
# 確認プロンプトなしで実行
./scripts/setup/setup-venv-deployment.sh --force

# ヘルスチェックのみ実行
./scripts/setup/setup-venv-deployment.sh --check-only

# サービスの再起動のみ
./scripts/setup/setup-venv-deployment.sh --restart-only

# 依存関係の更新のみ
./scripts/setup/setup-venv-deployment.sh --update-deps

# バックアップをスキップ
./scripts/setup/setup-venv-deployment.sh --skip-backup
```

## トラブルシューティング

### 仮想環境が見つからない

```bash
# 仮想環境を再作成
./scripts/setup/setup-venv-deployment.sh --force
```

### systemd サービスが起動しない

```bash
# サービス設定を更新
./scripts/setup/update-systemd-services.sh

# サービスを再起動
./scripts/setup/setup-venv-deployment.sh --restart-only
```

### 依存関係のインストールに失敗

```bash
# 仮想環境を手動でアクティベート
source ~/coordinate-recorder/venv/bin/activate

# pip をアップグレード
pip install --upgrade pip

# 依存関係を手動でインストール
pip install -r api/requirements.txt
pip install -r camera/requirements.txt
```

## 手動での仮想環境管理

スクリプトを使用せずに手動で管理する場合：

### 1. 仮想環境の作成

```bash
cd ~/coordinate-recorder
python3 -m venv venv
```

### 2. 仮想環境のアクティベート

```bash
source venv/bin/activate
```

### 3. 依存関係のインストール

```bash
pip install --upgrade pip
pip install -r api/requirements.txt
pip install -r camera/requirements.txt
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 4. systemd サービスの更新

```bash
# サービスファイルを編集
sudo nano /etc/systemd/system/coordinate-api.service

# ExecStart を仮想環境のパスに更新
ExecStart=/home/pi/coordinate-recorder/venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# systemd をリロード
sudo systemctl daemon-reload
sudo systemctl restart coordinate-api.service
```

## ベストプラクティス

1. **常に仮想環境を使用**: システム Python への直接インストールは避ける
2. **定期的な更新**: `setup-venv-deployment.sh --update-deps` で依存関係を更新
3. **バックアップ**: デプロイ前にバックアップを作成（スクリプトが自動実行）
4. **ヘルスチェック**: デプロイ後は必ずヘルスチェックを実行

## 関連ドキュメント

以前ここにあった 3 つのリンク（`raspberry-pi-setup.md` / `systemd-services.md` /
`../development/setup.md`）はいずれも**存在しないファイルを指していた**ため、実在するものに差し替えた（2026-07-27）。

- [依存関係管理ガイド](./dependency-management.md) — 現行の構成と手順
- [カメラセットアップ](./camera-setup.md) / [カメラ systemd](./camera-systemd.md)
- [systemd デプロイ](./systemd-deployment.md)
- [Raspberry Pi テストガイド](./raspberry_pi_test_guide.md)
