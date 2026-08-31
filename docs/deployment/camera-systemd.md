# カメラサービス systemd 設定

## 概要

カメラサービスを systemd サービスとして管理することで、以下の利点があります：

- **自動起動**: システム起動時に自動的にカメラサービスが開始
- **自動復旧**: クラッシュ時の自動再起動
- **ログ管理**: journald による統一的なログ管理
- **リソース管理**: メモリ・CPU 使用量の制限
- **プロセス管理**: 適切なシグナル処理と停止処理

## インストール方法

### 1. 自動インストール（推奨）

```bash
cd ~/coordinate-recorder
./scripts/install-camera-systemd.sh
```

### 2. 手動インストール

```bash
# サービスファイルをコピー
sudo cp ~/coordinate-recorder/systemd/coordinate-camera.service /etc/systemd/system/

# ラッパースクリプトに実行権限を付与
chmod +x ~/coordinate-recorder/scripts/systemd-camera-wrapper.sh

# systemd をリロード
sudo systemctl daemon-reload

# サービスを有効化（自動起動）
sudo systemctl enable coordinate-camera

# サービスを起動
sudo systemctl start coordinate-camera
```

## 使用方法

### サービス管理コマンド

```bash
# 状態確認
sudo systemctl status coordinate-camera

# 起動
sudo systemctl start coordinate-camera

# 停止
sudo systemctl stop coordinate-camera

# 再起動
sudo systemctl restart coordinate-camera

# 自動起動を有効化
sudo systemctl enable coordinate-camera

# 自動起動を無効化
sudo systemctl disable coordinate-camera
```

### ログ確認

```bash
# 最新のログを表示
sudo journalctl -u coordinate-camera -n 50

# リアルタイムでログを監視
sudo journalctl -u coordinate-camera -f

# 今日のログのみ表示
sudo journalctl -u coordinate-camera --since today

# エラーログのみ表示
sudo journalctl -u coordinate-camera -p err
```

## 設定内容

### サービスファイル構成

`/etc/systemd/system/coordinate-camera.service`:

- **Type=simple**: フォアグラウンドプロセスとして実行
- **Restart=always**: 常に再起動（クラッシュ時）
- **RestartSec=10**: 再起動前に 10 秒待機
- **MemoryLimit=512M**: メモリ使用量を 512MB に制限
- **CPUQuota=80%**: CPU 使用率を 80% に制限

### 環境変数

以下の環境変数がデフォルトで設定されます：

| 変数名       | デフォルト値                            | 説明                     |
| ------------ | --------------------------------------- | ------------------------ |
| CAMERA_PORT  | 8001                                    | カメラサービスのポート   |
| CAMERA_MODE  | hardware                                | カメラモード             |
| PIR_ENABLED  | true                                    | PIR センサーの有効/無効  |
| PIR_GPIO_PIN | 18                                      | PIR センサーの GPIO ピン |
| PHOTOS_DIR   | /home/pi/coordinate-recorder/photos | 写真保存ディレクトリ     |

カスタム設定は `/home/pi/coordinate-recorder/.env` ファイルで上書き可能です。

## トラブルシューティング

### サービスが起動しない場合

```bash
# 詳細なエラーログを確認
sudo journalctl -u coordinate-camera -xe

# 設定ファイルの構文チェック
sudo systemd-analyze verify coordinate-camera.service
```

### ポート競合エラー

```bash
# ポート 8001 を使用中のプロセスを確認
sudo lsof -i :8001

# 既存プロセスを停止
sudo fuser -k 8001/tcp
```

### 権限エラー

GPIO アクセスに必要なグループを確認：

```bash
# ユーザーが gpio, video グループに属しているか確認
groups unicco

# グループに追加（必要な場合）
sudo usermod -a -G gpio,video unicco
```

### メモリ不足

メモリ制限を調整：

```bash
# サービスファイルを編集
sudo systemctl edit coordinate-camera

# 以下を追加
[Service]
MemoryLimit=1G
```

## 既存のスクリプトとの互換性

`start-development.sh` などの既存スクリプトは systemd サービスの存在を自動検出し、以下の動作をします：

1. systemd サービスが存在し実行中 → そのまま使用
2. systemd サービスが存在するが停止中 → systemd 経由で起動
3. systemd サービスが存在しない → 従来通り直接起動

## アンインストール

```bash
# サービスを停止
sudo systemctl stop coordinate-camera

# 自動起動を無効化
sudo systemctl disable coordinate-camera

# サービスファイルを削除
sudo rm /etc/systemd/system/coordinate-camera.service

# systemd をリロード
sudo systemctl daemon-reload
```
