#!/bin/bash
# systemd サービス用カメラ起動ラッパー
# このスクリプトは systemd から呼び出され、適切な環境でカメラサービスを起動します

set -e

# プロジェクトルート設定
PROJECT_ROOT="/home/pi/coordinate-recorder"
cd "$PROJECT_ROOT"

# ログディレクトリ作成
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/photos"

# 環境変数ファイル読み込み（存在する場合）
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# 必須環境変数の設定（.env で設定されていない場合のデフォルト）
export CAMERA_PORT="${CAMERA_PORT:-8001}"
export CAMERA_MODE="${CAMERA_MODE:-hardware}"
export PIR_ENABLED="${PIR_ENABLED:-true}"
export PIR_GPIO_PIN="${PIR_GPIO_PIN:-18}"
export PHOTOS_DIR="${PHOTOS_DIR:-$PROJECT_ROOT/photos}"
export PYTHONUNBUFFERED=1
export PYTHONPATH="$PROJECT_ROOT/src:$PROJECT_ROOT:$PYTHONPATH"

# API URL の設定（必要に応じて）
export API_URL="${API_URL:-http://localhost:8000}"
export BACKEND_API_URL="${BACKEND_API_URL:-http://localhost:8000}"

# ログ出力
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Camera Service..."
echo "Configuration:"
echo "  CAMERA_PORT: $CAMERA_PORT"
echo "  CAMERA_MODE: $CAMERA_MODE"
echo "  PIR_ENABLED: $PIR_ENABLED"
echo "  PIR_GPIO_PIN: $PIR_GPIO_PIN"
echo "  PHOTOS_DIR: $PHOTOS_DIR"

# カメラサービス起動
exec /usr/bin/python3 "$PROJECT_ROOT/camera/camera_service.py"
