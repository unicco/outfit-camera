# カメラサービス設定ガイド

このドキュメントでは、Raspberry Pi で実際のカメラを使用するための設定手順を説明します。

## 目次

1. [環境変数の設定](#環境変数の設定)
2. [依存関係のインストール](#依存関係のインストール)
3. [systemd サービスの設定](#systemd-サービスの設定)
4. [トラブルシューティング](#トラブルシューティング)

## 環境変数の設定

### 重要な環境変数

```bash
# カメラモード（必須）
CAMERA_MODE=hardware  # 実際のカメラを使用

# 撮影画像の送信先。API は VPS で動くので Tailscale IP を指す
# （API_URL は後方互換のフォールバックなので新規に書かない）
BACKEND_API_URL=http://<VPS の Tailscale IP>:8000

# 写真保存ディレクトリ
PHOTOS_DIR=/home/pi/coordinate-recorder/photos
```

### 設定方法

1. `.env` ファイルで設定:

```bash
echo "CAMERA_MODE=hardware" >> ~/coordinate-recorder/.env
```

2. systemd サービスで直接設定（推奨）

## 依存関係のインストール

### システムパッケージ

```bash
# 必須パッケージをインストール
sudo apt update
sudo apt install -y \
    python3-opencv \
    python3-numpy \
    python3-libcamera \
    python3-picamera2 \
    python3-pillow \
    libcamera-apps \
    libcamera-dev \
    python3-fastapi \
    python3-uvicorn \
    python3-aiofiles

# 追加で必要なパッケージ
pip3 install --break-system-packages --user python-multipart python-dotenv
```

### 仮想環境での Picamera2 設定

Picamera2 を仮想環境で使用する場合は、システムサイトパッケージへのアクセスが必要です：

```bash
cd ~/coordinate-recorder/camera

# システムサイトパッケージを含む仮想環境を作成
rm -rf venv
python3 -m venv --system-site-packages venv

# 仮想環境を有効化
source venv/bin/activate

# カメラサービス固有の依存関係をインストール
pip install -r requirements.txt

# Picamera2 のインポートテスト
python -c "import picamera2; print('Picamera2 import successful')"
```

### インストールスクリプトの使用

```bash
cd ~/coordinate-recorder
./scripts/setup/install-camera-deps.sh
```

## systemd サービスの設定

<!-- verify: systemd/coordinate-camera.service 2026-07-31 -->

**unit を手書きしない。** 正は `systemd/coordinate-camera.service` で、`deploy/setup-pi.sh` が `/etc/systemd/system/` に配置する。

```bash
cd ~/coordinate-recorder
bash deploy/setup-pi.sh

sudo systemctl status coordinate-camera.service
```

手書きすると、unit が持つ以下がすべて失われる。

- `ExecStartPre` の 3 段（settle 待機 → pipewire のカメラデバイス解放待ち → Picamera2 の import 検査）
- PIR のチューニング値（`PIR_DETECTION_WINDOW=10` / `PIR_INACTIVITY_TIMEOUT=7`。既定値だと点灯しない・ムラが出る。）
- `GPIOZERO_PIN_FACTORY=lgpio`（PIR の読み取りに必要）
- `SupplementaryGroups=gpio video dialout`、`MemoryMax` / `CPUQuota`、`WantedBy=graphical.target`

unit の `[Service]` にはセキュリティ関連の設定も含まれる。**現行値と、その値である理由は `systemd/coordinate-camera.service` 内のコメントを読むこと。** 手書きの unit で置き換えると、そこに記録された判断ごと失われる。

**Python はシステム Python（`/usr/bin/python3`）を使う。** Picamera2 は apt でシステムに入るため、venv の Python を `ExecStart` に書くと `import picamera2` が通らない。

## カメラサービスのストリーミング機能

### エンドポイント

- `/health` - ヘルスチェック（カメラモードを含む）
- `/capture` - 写真撮影
- `/stream` - ライブストリーミング（MJPEG形式）

### ストリーミングの実装

カメラサービスは `/stream` エンドポイントでリアルタイムストリーミングを提供します。バックエンドAPIはこのストリームを中継してフロントエンドに配信します。

## トラブルシューティング

### 問題: シミュレーション映像が表示される

**原因**: `CAMERA_MODE` が正しく設定されていない、または Picamera2 が利用できない

**解決方法**:

1. 環境変数を確認:

```bash
sudo cat /proc/$(pgrep -f camera_service.py)/environ | tr '\0' '\n' | grep CAMERA_MODE
```

2. Picamera2 の動作確認:

```bash
cd ~/coordinate-recorder/camera
source venv/bin/activate
python -c "import picamera2; print('Picamera2 available')"
```

3. systemd サービスを再起動:

```bash
sudo systemctl restart coordinate-camera.service
```

### 問題: カメラサービスが起動しない

**原因1**: unit の `ExecStart` が古く、venv の Python を指している

**解決方法**:

```bash
# ExecStart を確認。/usr/bin/python3 でなければ古い
sudo systemctl cat coordinate-camera.service | grep ExecStart

# unit を配置し直す
cd ~/coordinate-recorder
bash deploy/setup-pi.sh
```

**原因2**: Picamera2 関連モジュールが不足している

**解決方法**:

```bash
# システムパッケージを再インストール
sudo apt install -y python3-libcamera python3-picamera2

# 仮想環境を再作成
cd ~/coordinate-recorder/camera
rm -rf venv
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements.txt

# ログを確認
sudo journalctl -u coordinate-camera.service -f
```

### 問題: systemd サービスで "No such file or directory" エラー

**原因**: `/etc/systemd/system/` の unit が古い。リポジトリの `systemd/coordinate-camera.service` と食い違っている。

`ExecStart` は**システム Python**（`/usr/bin/python3`）でなければならない。venv の Python を指していたら、それが原因。Picamera2 は apt でシステムに入るため venv からは import できない。

**解決方法**: unit を手で書き換えず、配置し直す。

```bash
cd ~/coordinate-recorder
bash deploy/setup-pi.sh

sudo systemctl status coordinate-camera.service
```

### 問題: ストリームが表示されない

**原因**: バックエンドAPIがカメラサービスに接続できない

**確認方法**:

```bash
# カメラサービスの動作確認
curl http://localhost:8001/health
curl http://localhost:8001/stream --max-time 2

# バックエンドAPIの確認
curl http://localhost:8000/camera/stream --max-time 2
```

### デバッグスクリプトの使用

```bash
# 詳細なデバッグ情報を表示
./scripts/debug/debug-camera.sh
```

このスクリプトは以下を確認します：

- libcamera デバイスの状態
- ユーザー権限
- Python モジュールのインストール状態
- カメラハードウェアの検出状態
- サービスのログ

## ベストプラクティス

1. **環境変数は systemd サービスで明示的に設定する**

   - `.env` ファイルに依存しない
   - `CAMERA_MODE=hardware` を必ず設定

2. **本番のカメラサービスはシステム Python で動かす**

   - unit の `ExecStart` は `/usr/bin/python3`。venv を挟まない
   - Picamera2・libcamera・gpiozero・lgpio は apt が提供する。pip で入れると `~/.local` に二重に入って apt 版と競合する

3. **ローカルで venv を使うなら --system-site-packages で作成する**

   - 手元で `camera/` を動かすときだけの話。本番 Pi には効かない
   - Pi の依存が未宣言な件は別途扱う

4. **ログを活用する**

   - `journalctl` でサービスログを確認
   - エラーメッセージから問題を特定

5. **定期的な動作確認**
   - `/health` エンドポイントで状態確認
   - カメラモードが正しいことを確認
   - Picamera2 の初期化成功メッセージを確認

## まとめ

カメラサービスの設定で重要なポイント：

1. **CAMERA_MODE=hardware** を必ず設定
2. **python3-libcamera** / **python3-picamera2** を apt でインストール
3. unit は手書きせず `deploy/setup-pi.sh` に配置させる
4. ログとデバッグツールを活用

これらの設定により、Raspberry Pi で実際のカメラからの映像を使用した安定したカメラサービスを運用できます。

### 成功時のログ例

正常に動作している場合、以下のようなログが出力されます：

```
python[PID]: 2025-07-02 10:51:51,249 - picamera2.picamera2 - INFO - Camera started
python[PID]: 2025-07-02 10:51:51,249 - __main__ - INFO - Applying initial camera settings...
python[PID]: 2025-07-02 10:51:51,249 - __main__ - INFO - Picamera2 initialization completed successfully
python[PID]: INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```
