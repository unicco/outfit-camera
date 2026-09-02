#!/bin/bash
# 重要な依存関係だけをチェックして、不足分のみインストール

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_CACHE_DIR="${VENV_CACHE_DIR:-$REPO_ROOT/.venvs}"
VENV_PATH="${VENV_PATH:-$VENV_CACHE_DIR/api-server-dd0c3437492e8df90c3c3ea9b27923de}"

if [ ! -x "$VENV_PATH/bin/pip" ]; then
    echo "❌ pip not found: $VENV_PATH/bin/pip" >&2
    exit 1
fi

# 必須パッケージリスト
CRITICAL_PACKAGES=(
    "psutil"
    "fastapi"
    "uvicorn"
    "sqlalchemy"
    "psycopg2-binary"
    "rembg"
    "httpx"
    "pillow"
)

echo "🔍 Checking critical dependencies..."
MISSING_PACKAGES=()

for package in "${CRITICAL_PACKAGES[@]}"; do
    if ! "$VENV_PATH/bin/pip" show "$package" >/dev/null 2>&1; then
        MISSING_PACKAGES+=("$package")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -eq 0 ]; then
    echo "✅ All critical dependencies are installed!"
else
    echo "📦 Installing missing packages: ${MISSING_PACKAGES[*]}"
    "$VENV_PATH/bin/pip" install "${MISSING_PACKAGES[@]}"
    echo "✅ Done!"
fi
