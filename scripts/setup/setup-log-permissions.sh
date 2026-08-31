#!/bin/bash

# ログディレクトリの権限設定スクリプト
# 本番環境でのセットアップ時に sudo で実行

set -e

LOG_DIR="/var/log/coordinate-recorder"
USER="pi"
GROUP="pi"

echo "🔧 Setting up log directory permissions..."

# ログディレクトリの作成
if [ ! -d "$LOG_DIR" ]; then
    echo "📁 Creating log directory: $LOG_DIR"
    mkdir -p "$LOG_DIR"
fi

# 権限設定
echo "🔐 Setting ownership to $USER:$GROUP"
chown -R "$USER:$GROUP" "$LOG_DIR"

echo "🔐 Setting permissions to 755"
chmod 755 "$LOG_DIR"

# 確認
if [ -d "$LOG_DIR" ] && [ -w "$LOG_DIR" ]; then
    echo "✅ Log directory setup completed successfully"
    ls -la "$LOG_DIR"
else
    echo "❌ Failed to set up log directory"
    exit 1
fi

echo "ℹ️  Note: Run this script with sudo during initial setup"
