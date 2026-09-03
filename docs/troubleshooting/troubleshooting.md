# トラブルシューティングガイド

このドキュメントは、開発中に遭遇した問題とその解決方法をまとめたものです。

## Playwright セッション管理

### 空白ページが表示される

**問題**: Claude Code で MCP Playwright を使用すると空白ページが表示される

**原因**: 古い MCP Chrome プロファイルの競合

**解決方法**:

```bash
./scripts/debug/playwright-session-cleanup.sh
```

### "Browser is already in use" エラー

**問題**:

```
Error: Browser is already in use for $HOME/Library/Caches/ms-playwright/mcp-chrome-profile
```

**原因**: 前回のセッションのブラウザプロセスが残存

**解決方法**:

```bash
# 1. プロセス確認
ps aux | grep -i "chrome\|chromium\|playwright"

# 2. クリーンアップ実行
./scripts/debug/playwright-session-cleanup.sh
```

**詳細**: `scripts/debug/playwright-session-cleanup.sh` の実装を参照

## カメラサービス関連

### Picamera2 インポートエラー

**問題**: カメラサービスが "ModuleNotFoundError: No module named 'libcamera'" エラーで起動しない

**原因**:

- 仮想環境でシステムサイトパッケージにアクセスできない
- libcamera システムパッケージがインストールされていない

**解決方法**:

1. システムパッケージをインストール:

   ```bash
   sudo apt install -y python3-libcamera python3-picamera2
   ```

2. 仮想環境を --system-site-packages で再作成:

   ```bash
   cd ~/coordinate-recorder/camera
   rm -rf venv
   python3 -m venv --system-site-packages venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Picamera2 のインポートテスト:
   ```bash
   python -c "import picamera2; print('Success')"
   ```

### systemd サービス起動エラー

**問題**: カメラサービスが "No such file or directory" エラーで起動しない

**原因**:

- `/etc/systemd/system/` の unit が古く、`ExecStart` が venv の Python を指している
- 正は `systemd/coordinate-camera.service` の `/usr/bin/python3`（システム Python）

**解決方法**:

1. `ExecStart` がシステム Python かを確認:

   ```bash
   sudo systemctl cat coordinate-camera.service | grep ExecStart
   ```

   `/usr/bin/python3` でなく venv の Python を指していたら、それが原因。Picamera2 は apt でシステムに入るため venv からは import できない。

2. unit を手で書き換えず、配置し直す:

   ```bash
   cd ~/coordinate-recorder
   bash deploy/setup-pi.sh
   ```

3. ログで確認:
   ```bash
   sudo journalctl -u coordinate-camera.service -f
   ```

### カメラが認識されない

**問題**: ハードウェアモードでもシミュレーション映像が表示される

**原因**:

- カメラハードウェアが接続されていない
- カメラインターフェースが無効になっている

**解決方法**:

1. カメラデバイスを確認:

   ```bash
   ls /dev/video*
   libcamera-hello --list-cameras
   ```

2. カメラインターフェースを有効化:

   ```bash
   sudo raspi-config
   # Interface Options > Camera > Enable
   ```

3. カメラサービスを再起動:
   ```bash
   sudo systemctl restart coordinate-camera.service
   ```

### カメラサービス起動失敗

**問題**: カメラサービスが起動時に失敗し、ログに依存関係エラーが表示される

**原因**:

- 必要な Python パッケージがインストールされていない
- 仮想環境が正しく設定されていない
- 環境変数が不適切
- Raspberry Pi 固有の依存関係が欠如

**診断方法**:

1. カメラサービス診断スクリプトを実行:

   ```bash
   ./scripts/debug/camera-startup-check.sh
   ```

2. ログファイルを確認:

   ```bash
   tail -50 ./logs/camera*service.log
   ```

**解決方法**:

1. **Python依存関係の修復**:

   ```bash
   cd camera
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Raspberry Pi固有の依存関係**:

   ```bash
   # システムパッケージをインストール
   sudo apt update
   sudo apt install -y python3-picamera2 python3-libcamera

   # 仮想環境を --system-site-packages で再作成
   rm -rf venv
   python3 -m venv --system-site-packages venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **環境変数の確認**:

   ```bash
   # 必要な環境変数が設定されているか確認
   echo "CAMERA_PORT: $CAMERA_PORT"
   echo "CAMERA_MODE: $CAMERA_MODE"
   echo "API_URL: $API_URL"
   echo "PHOTOS_DIR: $PHOTOS_DIR"
   ```

4. **手動起動テスト**:

   ```bash
   cd camera
   source venv/bin/activate
   python3 camera_service.py
   ```

**よくあるエラーと対処法**:

- `ModuleNotFoundError: No module named 'cv2'`: OpenCV未インストール → `pip install opencv-python`
- `ModuleNotFoundError: No module named 'picamera2'`: Raspberry Pi依存関係未インストール → システムパッケージを上記手順でインストール
- `Address already in use`: ポート競合 → `lsof -i :8001` でプロセス確認し終了
- `Permission denied`: ディレクトリアクセス権限問題 → 適切なディレクトリパスを環境変数で設定

### google-generativeai インポートエラー

**問題**: coordinate-camera サービスが "ModuleNotFoundError: No module named 'google.generativeai'" エラーで起動しない

**原因**:

- systemd サービスがシステム Python を使用しており、仮想環境のパッケージにアクセスできない
- Picamera2 の制約により、システム Python を使用する必要がある

**解決方法**:

1. システムレベルでのインストール（推奨）:

```bash
# Raspberry Pi にSSH接続
ssh user@pi-camera.local

# システムレベルで google-generativeai をインストール
sudo pip3 install --break-system-packages google-generativeai==0.8.5
```

2. カメラサービスの再起動:

```bash
sudo systemctl restart coordinate-camera
```

**注意**:

- `--break-system-packages` フラグは Debian 12 (Bookworm) 以降で必要
- システムパッケージマネージャーとの競合を避けるため、特定のバージョンを指定

## Google Photos 関連

### Request had insufficient authentication scopes エラー

**問題**: Google Photos アップロード時に "Request had insufficient authentication scopes" エラーが発生

**原因**:

- Google Photos API トークンが古いスコープで生成されている
- アルバム作成やメディアアップロードに必要な権限が不足

**解決方法**:

1. 既存のトークンを削除して再生成:

```bash
# Raspberry Pi にSSH接続
ssh user@pi-camera.local

# coordinate-recorder ディレクトリに移動
cd /home/pi/coordinate-recorder

# 既存のトークンを削除
rm -f google_photos_token.json

# API サービスを再起動
sudo systemctl restart coordinate-api
```

2. 新しいトークンを生成:

```bash
# ブラウザで以下のURLにアクセス（要認証）
# http://pi-camera.local:8000/docs

# Google Photos 認証エンドポイントを使用して再認証
```

3. 必要な権限を許可:

- Google フォト ライブラリの表示
- Google フォト ライブラリへの追加
- Google フォト ライブラリ内のアイテムの共有

**注意**:

- 新しいスコープが追加されたため、Google アカウント設定でアプリのアクセスをリセットする必要がある場合があります
- Google アカウント設定 > セキュリティ > サードパーティ製アプリとサービス で確認

## ネットワーク関連

### ポート競合問題

**問題**: API へのアクセスが "Connection reset by peer" エラーになる

**原因**:

- SSH トンネルやその他のプロセスがポートを占有している
- 特に `stable-tunnel.sh` などの自動化スクリプトが原因の場合が多い

**解決方法**:

```bash
# ポートを使用しているプロセスを確認
lsof -i :8000 | grep LISTEN
ps aux | grep -E "(ssh.*8000|stable-tunnel)"

# プロセスを終了
kill -9 <PID>
```

## FastAPI 関連

### ルーティングのデバッグ

**スタートアップ時のルート確認**:

```python
@app.on_event("startup")
async def startup_event():
    print("\n=== REGISTERED ROUTES AT STARTUP ===")
    for route in app.routes:
        if hasattr(route, 'path'):
            methods = getattr(route, 'methods', 'N/A')
            print(f"  {route.path}: {methods}")
    print(f"Total routes: {len([r for r in app.routes if hasattr(r, 'path')])}")
    print("==================================\n")
```

### 依存性注入のエラー

**問題**: `TypeError: function() got multiple values for argument 'xxx'`

**原因**: FastAPI の `Depends` で注入されるパラメータを手動でも渡している

**解決方法**:

```python
# ❌ 間違い: 手動で依存関数を呼び出す
db = next(get_db())
result = some_function(db, ...)

# ✅ 正しい: Depends で注入してそのまま渡す
async def endpoint(db: Session = Depends(get_db)):
    result = await some_function(db=db, ...)
```

## 環境変数・設定関連

### GCS (Google Cloud Storage) 設定エラー

**問題**: `IsADirectoryError: [Errno 21] Is a directory: '/app/gcs-key.json'`

**原因**:

- GCS 認証ファイルが正しくマウントされていない
- ファイルパスがディレクトリとして作成されている

**解決方法**:

1. ローカルストレージモードに切り替える
   ```bash
   export STORAGE_TYPE=local
   ```

## 開発環境セットアップ関連

### Web サーバー起動後の必須確認

**重要**: Web サーバーを新規起動または再起動した場合、必ず以下の手順で動作確認を行ってください：

```bash
# API サーバーの場合
curl -f http://localhost:8000/health
# または
curl -f http://localhost:8000/docs

# Camera サーバーの場合
curl -f http://localhost:8001/health
curl -f http://localhost:8001/stream --max-time 2

# UI サーバーの場合
curl -f http://localhost:3000
# または
curl -I http://localhost:3000
```

- **必須**: HTTP ステータス 200 が返ってくることを確認
- 確認完了まで作業を完了とみなさない

### よくある環境設定エラー

#### Permission denied エラー

**問題**: `Permission denied: /var/log/coordinate-recorder`

**解決方法**:

```bash
# 環境変数でログディレクトリを指定
export BACKEND_LOG_DIR=./logs
```

#### 写真が表示されない

**問題**: UI で写真が表示されない

**解決方法**:

```bash
# 正しい写真ディレクトリパスを設定
export PHOTOS_DIR="$PWD/photos"
```

#### Address already in use

**問題**: ポートが既に使用されている

**解決方法**:

```bash
# 使用中のプロセスを特定・終了
lsof -i :8000 | grep LISTEN
pkill -f "uvicorn.*8000"
```

## ネットワーク・接続関連

### フロントエンド接続問題

**問題**: ブラウザからアクセス時の ERR_BLOCKED_BY_CLIENT エラー

**原因**: フロントエンドが Pi ホスト名ではなく `localhost` に接続しようとしている

**解決方法**:

```bash
# 環境変数を更新
export VITE_API_URL=http://pi-camera.local:8000
export VITE_CAMERA_URL=http://pi-camera.local:8001

# サーバーを再起動
./scripts/stop-development.sh
./scripts/start-development.sh
```

### カメラサービスのバックエンド接続

**問題**: カメラは写真を撮影するがバックエンドに送信しない

**原因**: 送信先が VPS の API を指していない。API は Pi ではなく VPS で動くので、`localhost` は誤り。

**解決方法**: unit を手編集せず、Pi の `.env` に `BACKEND_API_URL` を書く（`API_URL` は後方互換のフォールバックなので新規に書かない）。

```bash
# ~/coordinate-recorder/.env
# BACKEND_API_URL=http://<VPS の Tailscale IP>:8000

sudo systemctl restart coordinate-camera.service

# 疎通確認
curl -f http://<VPS の Tailscale IP>:8000/health
```

## システム診断・検証手法

### 包括的なシステムヘルスチェック

```bash
# 包括的な検証を実行
./scripts/debug/verify-environment.sh

# 個別のサービスをチェック
sudo systemctl status coordinate-camera.service
./scripts/debug/verify-environment.sh
```

### クイック診断

```bash
# 全サービスが実行中であることを確認
sudo systemctl status coordinate-camera.service
./scripts/debug/verify-environment.sh

# API エンドポイントをテスト
curl -f http://localhost:8001/capture  # カメラサービス
curl -f http://localhost:8000/docs     # バックエンド API
curl -f http://pi-camera.local:3000  # フロントエンド

# 環境変数をチェック
echo "VITE_API_URL: $VITE_API_URL"
echo "VITE_CAMERA_URL: $VITE_CAMERA_URL"
```

## GitHub・Git 関連

### Issue 検索エラー対策

**問題**: "issue not found" レスポンスが返される

**解決方法**: 以下の検索戦略を使用

1. **主要方法**: GitHub CLI コマンドを使用

   ```bash
   # アクセス確認のため最近の issue をリスト
   gh issue list --limit 20

   # 番号で特定の issue を検索
   gh issue view <number>

   # キーワードで issue を検索
   gh issue list --search "<keywords>" --limit 10
   ```

2. **代替方法**: gh CLI が失敗した場合、Web 検索を使用

### Git 操作のタイムアウト対策

**問題**: Git 操作がタイムアウトする

**解決方法**: Bash ツールでタイムアウトを延長

```bash
# デフォルト（2分）
git pull origin main

# 5分に延長が推奨される操作
git clone <large-repo>     # timeout=300000
docker build --no-cache   # timeout=300000
npm run test:e2e          # timeout=600000 (最大10分)
```

## デバッグ手法

### エンドポイントの動作確認

1. **OpenAPI ドキュメントで確認**

   ```bash
   curl -s http://localhost:8000/openapi.json | jq '.paths | keys' | grep "your-endpoint"
   ```

2. **Python スクリプトで直接テスト**

   ```bash
   cd api
   source venv/bin/activate
   python -c "import requests; print(requests.get('http://localhost:8000/your-endpoint').json())"
   ```

## よくあるエラーパターン

### CORS エラー

**問題**: ブラウザからのリクエストが CORS policy でブロックされる

**確認方法**:

- ブラウザの開発者ツールでネットワークタブを確認
- プリフライトリクエスト (OPTIONS) のレスポンスを確認

**解決方法**:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開発環境のみ
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### pre-commit hook の失敗

**問題**: コミット時に gitleaks が秘密情報を検出して止まる

```
[pre-commit] gitleaks found secrets in staged changes (see above).
```

**解決方法**: 検出箇所を確認し、実際の秘密情報なら staged から外して `.env` 等へ移す。**誤検知だと確認できた場合のみ**バイパスする。

```bash
GITLEAKS_SKIP=1 git commit -m "your message"
```

`ruff` / `black` / `mypy` はコミット時には走りません。CI の "Fast Quality Checks" で落ちた場合は `npm run checks` をローカルで叩いてください（詳細は `docs/development/local-quality-checks.md`）。

## AI 検出・ワードローブマッチング関連

### scikit-learn 依存関係エラー

**問題**: ワードローブマッチング機能で "No module named 'sklearn'" エラーが発生

**症状**:

- AI 検出は正常に動作（バウンディングボックス表示される）
- ワードローブマッチング候補が 0 件になる
- ログに `ModuleNotFoundError: No module named 'sklearn'` が出力

**原因**:

- ワードローブマッチング機能で scikit-learn を使用しているが、環境にインストールされていない
- 色の類似度計算（cosine similarity）で scikit-learn が必要

**解決方法**:

1. **手動インストール** (即座の対応):

   ```bash
   # API サーバーの仮想環境で scikit-learn をインストール
   cd api
   source venv/bin/activate
   pip install scikit-learn
   ```

2. **自動インストール** (推奨・将来の予防):

   ```bash
   # 開発環境起動スクリプトが scikit-learn を自動インストール
   ./scripts/start-development.sh
   ```

3. **本番環境での対応**:
   ```bash
   # Raspberry Pi 本番環境
   ssh user@pi-camera.local
   cd /home/pi/coordinate-recorder/api
   source venv/bin/activate
   pip install scikit-learn
   sudo systemctl restart coordinate-camera.service
   ```

**検証方法**:

```bash
# scikit-learn のインポートテスト
python -c "import sklearn; print('scikit-learn version:', sklearn.__version__)"

# ワードローブマッチング機能のテスト
curl -X POST http://localhost:8000/api/v2/ai/detect \
  -H "Content-Type: application/json" \
  -d '{"photo_id": "test_photo_id", "match_wardrobe": true}'
```

**関連ファイル**:

- `requirements-api.txt` - scikit-learn 依存関係定義（`scikit-learn>=1.3.0`）
- `api/app/wardrobe_service.py:22` - scikit-learn インポート
- `api/app/routers/ai_detection.py` - ワードローブマッチング処理
- `scripts/start-development.sh:158-165` - 自動依存関係チェック

### PYTHONPATH 設定エラー

**問題**: `coordinate_recorder` モジュールが見つからない

**症状**:

- `ImportError: No module named 'coordinate_recorder'` エラー
- AI 検出機能が起動時に失敗

**原因**:

- PYTHONPATH 環境変数が正しく設定されていない
- Worktree 環境で古いパス設定を使用している

**解決方法**:

1. **環境設定ファイルの更新**:

   ```bash
   # api/.env.local の PYTHONPATH を確認・更新
   PYTHONPATH=./src:.
   ```

2. **開発環境起動スクリプトの使用**:
   ```bash
   # PYTHONPATH を自動設定
   ./scripts/start-development.sh
   ```

**検証方法**:

```bash
# モジュールインポートテスト
cd api
source venv/bin/activate
python -c "from api.app.routers.ai_detection import ClothingDetectorV2; print('Import successful')"
```

## Issue 260: Chromium プロセスメモリ問題対応

### 問題概要

**Issue**: Playwright 自動化による Chromium プロセスが大量のメモリを消費し、API サーバーが不安定化

**症状**:

- E2E テスト実行後、Chromium プロセスが残存しメモリリークが発生
- API サーバーのレスポンス遅延、最悪の場合クラッシュ
- システム全体のメモリ使用量が高止まり

**根本原因**:

- Playwright のデフォルト設定では非ヘッドレスモードでメモリ使用量が高い
- ブラウザプロセスの適切なクリーンアップが行われていない
- 並列テスト実行時のリソース制限不足

### 対応策

#### 1. メモリ最適化設定

**Playwright 設定** (`playwright.config.js`):

```javascript
module.exports = {
  workers: 1, // 並列実行数制限
  use: {
    headless: true, // ヘッドレスモード
    launchOptions: {
      args: [
        "--max-old-space-size=256", // メモリ制限
        "--memory-pressure-off",
        "--no-sandbox",
        "--disable-dev-shm-usage",
      ],
    },
  },
};
```

**Python Playwright スクリプト最適化**:

```python
browser = await p.chromium.launch(
    headless=True,  # メモリ使用量削減
    args=[
        '--max-old-space-size=256',
        '--memory-pressure-off',
        '--no-sandbox',
        '--disable-dev-shm-usage'
    ]
)
```

#### 2. プロセス監視・クリーンアップ

**自動クリーンアップ** (`scripts/stop-development.sh`):

```bash
# Chromium プロセスの段階的終了
chromium_pids=$(pgrep -f "chrome|chromium|playwright" || true)
if [ -n "$chromium_pids" ]; then
    # SIGTERM で graceful shutdown
    echo "$chromium_pids" | xargs -r kill -TERM
    sleep 3

    # 残存プロセスを SIGKILL
    remaining_pids=$(pgrep -f "chrome|chromium|playwright" || true)
    if [ -n "$remaining_pids" ]; then
        echo "$remaining_pids" | xargs -r kill -KILL
    fi
fi
```

**プロセス監視ツール**:

```bash
./scripts/debug/check-browser-processes.sh
```

#### 3. テスト環境リソース管理

**グローバルセットアップ/ティアダウン**:

- `tests/e2e/global-setup.js` - テスト開始前の環境準備
- `tests/e2e/global-teardown.js` - テスト完了後のクリーンアップ

### 検証・モニタリング

```bash
# プロセス監視
./scripts/debug/check-browser-processes.sh

# メモリ使用量確認
ps aux | grep -E "(chrome|chromium)" | awk '{sum+=$6} END {print "Total RSS: " sum/1024 " MB"}'

# 自動クリーンアップテスト
./scripts/stop-development.sh
```

### 予防策

1. **定期的な監視**: 開発中は定期的にブラウザプロセスをチェック
2. **適切な終了**: 開発セッション終了時は `./scripts/stop-development.sh` でクリーンアップ
3. **設定確認**: 新しい E2E テスト追加時はメモリ設定を確認

### 関連ファイル

- `api/debug/check_ui_with_playwright.py` - Python Playwright 最適化
- `playwright.config.js` - Playwright 全体設定最適化
- `scripts/stop-development.sh` - ブラウザプロセスクリーンアップ
- `scripts/debug/check-browser-processes.sh` - プロセス監視ツール
- `tests/e2e/global-setup.js` - テスト環境セットアップ
- `tests/e2e/global-teardown.js` - テスト環境クリーンアップ

## UI の URL 設定問題

### 問題: タッチスクリーン UI でカメラストリームや API 接続エラーが発生

**症状**:

- カメラストリームが「coordinate.unicco.app でストリームしようとしています」エラー
- タッチスクリーンから写真保存時に「error occurred」
- ブラウザコンソールで localhost への接続拒否エラー

**原因**:

- UI ビルド時の環境変数（VITE_API_URL、VITE_CAMERA_URL）が誤った URL を指している
- .env.production に外部 URL（https://coordinate.unicco.app）が設定されていた
- ビルド済の JavaScript に古い URL がハードコードされている

**解決方法**:

1. **環境変数の確認と修正**:

   ```bash
   # 本番機の .env を確認
   grep -E "VITE_API_URL|VITE_CAMERA_URL" /home/pi/coordinate-recorder/.env

   # 正しい設定（Raspberry Pi の場合）
   VITE_API_URL=http://pi-camera.local:8000
   VITE_CAMERA_URL=http://pi-camera.local:8001

   # localhost アクセスの場合
   # VITE_API_URL=http://localhost:8000
   # VITE_CAMERA_URL=http://localhost:8001
   ```

2. **UI の再ビルドとデプロイ**:

   ```bash
   cd /home/pi/coordinate-recorder/ui
   rm -rf dist
   npm run build
   sudo rm -rf /var/www/coordinate-recorder-ui/*
   sudo cp -r dist/* /var/www/coordinate-recorder-ui/
   sudo systemctl restart coordinate-kiosk
   ```

3. **環境変数の管理方法**:
   - `.env.production` は削除（不要）
   - すべての環境固有設定は `.env` で管理
   - 新環境では `.env.template` をコピーして `.env` を作成

**予防策**:

- URL 設定は常に `.env` で管理し、git にコミットしない
- `.env.production` に環境固有の URL を含めない
- ビルド前に必ず `.env` の URL 設定を確認

**確認方法**:

```bash
# ビルド済ファイルに誤った URL が含まれていないか確認
grep -l "coordinate.unicco.app" /var/www/coordinate-recorder-ui/assets/*.js

# カメラストリーミングの動作確認
curl -s http://pi-camera.local:8001/stream | head -c 100
```

## React 開発環境関連

### Vite 本番ビルドで console.log が削除される問題

**問題**: 本番環境で console.log が一切出力されない

**症状**:
- デバッグ用に追加した console.log が本番環境で動作しない
- API レスポンスの確認やデバッグが困難
- ブラウザの開発者ツールに何も表示されない

**原因**:
- Vite のデフォルト設定では、本番ビルドで console と debugger を削除する
- `vite.config.ts` の esbuild.drop 設定が `['console', 'debugger']` になっている

**解決方法**:

1. **vite.config.ts を修正**:
   ```typescript
   esbuild: {
     // TypeScript のトランスパイルを高速化
     target: 'es2020',
     // 本番環境でも console は残す（debugger のみ削除）
     drop: ['debugger'],
   },
   ```

2. **以前の設定（問題のある設定）**:
   ```typescript
   esbuild: {
     target: 'es2020',
     drop: mode === 'production' ? ['console', 'debugger'] : ['debugger'],
   },
   ```

**影響**:
- 本番環境でもデバッグログが出力されるようになる
- パフォーマンスへの影響は最小限
- セキュリティ上の懸念がある場合は、機密情報を console.log に含めないよう注意

**確認方法**:
```bash
# ビルド後のファイルで console.log が含まれているか確認
grep -n "console.log" dist/assets/*.js | head -5

# または本番環境でブラウザコンソールを開いて確認
```

---

このドキュメントは随時更新されます。新しい問題と解決方法を発見した場合は、このファイルに追記してください。
