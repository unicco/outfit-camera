# Python 仮想環境の使用について

> [!NOTE]
> **Pi の camera は仮想環境を使っていない**（2026-07-27 確認）。本文 L49 の「`coordinate-camera.service`: システム Python を使用」が現行の実態で、「Picamera2 などは仮想環境内でも正常に動作します」という記述は Pi の本番には当てはまらない（`~/coordinate-recorder/camera/venv` は `bin/python` を持たない空ディレクトリとして残っている）。
>
> Pi の実体は apt（picamera2 / gpiozero / lgpio）+ 手動 `pip install --user` の `~/.local`。宣言されていない状態で、別途扱う。

## 概要

本プロジェクトは Python の仮想環境を使用して依存関係を管理します。これにより、システムの Python パッケージとプロジェクトの依存関係を分離し、バージョンの競合を防ぎます。

## 背景

Debian/Ubuntu の新しいバージョンでは、システムパッケージの保護のため `pip` の直接使用が制限されています（PEP 668）。このため、仮想環境を使用することが推奨されています。

## セットアップ

### 自動セットアップ

systemd サービスは初回起動時に自動的に仮想環境を作成し、必要な依存関係をインストールします。

### 手動セットアップ

```bash
# セットアップスクリプトを実行
cd /home/pi/coordinate-recorder
./scripts/setup/setup-venv.sh
```

## 仮想環境の場所

- **パス**: `/home/pi/coordinate-recorder/venv`
- **Python 実行ファイル**: `/home/pi/coordinate-recorder/venv/bin/python`
- **pip**: `/home/pi/coordinate-recorder/venv/bin/pip`

## 手動での仮想環境の使用

```bash
# 仮想環境を有効化
source /home/pi/coordinate-recorder/venv/bin/activate

# パッケージのインストール
pip install -r requirements-api.txt

# 仮想環境を無効化
deactivate
```

## systemd サービスでの使用

systemd サービスファイルの Python 環境：

- `coordinate-api.service`: 仮想環境の Python を使用（Pydantic 2.x のため）
- `coordinate-camera.service`: システム Python を使用（Picamera2 はシステムレベルでのみ利用可能）

## トラブルシューティング

### 仮想環境の再作成

```bash
# 既存の仮想環境を削除
rm -rf /home/pi/coordinate-recorder/venv

# サービスを再起動（自動的に再作成される）
sudo systemctl restart coordinate-api
sudo systemctl restart coordinate-camera
```

### 依存関係の更新

```bash
cd /home/pi/coordinate-recorder
source venv/bin/activate
pip install --upgrade -r requirements-api.txt
pip install --upgrade -r camera/requirements.txt
```

## 注意事項

- Picamera2 などのシステム依存のパッケージは、仮想環境内でも正常に動作します
- GPIO アクセスは仮想環境でも問題ありません
- 仮想環境は各サービスの初回起動時に自動的に作成されます
