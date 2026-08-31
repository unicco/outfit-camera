#!/bin/bash

# Python 仮想環境のセットアップスクリプト
# systemd サービスで使用される仮想環境を作成し、依存関係をインストール

set -e

# スクリプトのディレクトリを取得
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🐍 Python Virtual Environment Setup"
echo "=================================="

# Python3 と venv モジュールの確認
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed"
    exit 1
fi

if ! python3 -c "import venv" &> /dev/null; then
    echo "❌ Python3 venv module is not installed"
    echo "Please install: sudo apt-get install python3-venv"
    exit 1
fi

# 仮想環境の作成
VENV_PATH="$PROJECT_ROOT/venv"

if [ -d "$VENV_PATH" ]; then
    echo "⚠️  Virtual environment already exists at $VENV_PATH"
    echo "Do you want to recreate it? (y/N)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "🗑️  Removing existing virtual environment..."
        rm -rf "$VENV_PATH"
    else
        echo "Using existing virtual environment"
    fi
fi

if [ ! -d "$VENV_PATH" ]; then
    echo "📦 Creating virtual environment at $VENV_PATH"
    python3 -m venv "$VENV_PATH"
    echo "✅ Virtual environment created"
fi

# 仮想環境を有効化
echo "🔄 Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# pip のアップグレード
echo "📦 Upgrading pip..."
pip install --upgrade pip

# API 依存関係のインストール
if [ -f "$PROJECT_ROOT/requirements-api.txt" ]; then
    echo "📦 Installing API dependencies..."
    pip install -r "$PROJECT_ROOT/requirements-api.txt"
    echo "✅ API dependencies installed"
else
    echo "⚠️  requirements-api.txt not found"
fi

# カメラサービス依存関係のインストール
if [ -f "$PROJECT_ROOT/camera/requirements.txt" ]; then
    echo "📦 Installing camera service dependencies..."
    pip install -r "$PROJECT_ROOT/camera/requirements.txt"
    echo "✅ Camera service dependencies installed"
else
    echo "⚠️  camera/requirements.txt not found"
fi

# 共通ライブラリのインストール
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    echo "📦 Installing common dependencies..."
    pip install -r "$PROJECT_ROOT/requirements.txt"
    echo "✅ Common dependencies installed"
fi

# インストールされたパッケージの確認
echo ""
echo "📋 Checking critical packages:"
for pkg in pydantic fastapi uvicorn httpx; do
    if python -c "import $pkg" 2>/dev/null; then
        version=$(python -c "import $pkg; print($pkg.__version__)" 2>/dev/null || echo "unknown")
        echo "✅ $pkg: $version"
    else
        echo "❌ $pkg: Not installed or import failed"
    fi
done

echo ""
echo "✅ Virtual environment setup complete!"
echo ""
echo "To activate the virtual environment manually, run:"
echo "  source $VENV_PATH/bin/activate"
echo ""
echo "systemd services will automatically use this virtual environment."
