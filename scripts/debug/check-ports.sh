#!/bin/bash

# ポート使用状況確認スクリプト
# 開発でよく使用されるポートの状況を確認

echo "=== 開発ポート使用状況 ==="
echo

# チェックするポート一覧
PORTS=(
    "3000:React開発サーバー（代替）"
    "5173:Vite開発サーバー（UI）"
    "5174:Vite開発サーバー（API Session用）"
    "5175:Vite開発サーバー（Camera Session用）"
    "5176:Vite開発サーバー（AI Session用）"
    "5177:Vite開発サーバー（Deploy Session用）"
    "8000:FastAPI（Backend）"
    "8001:Camera Service"
    "8080:代替APIポート"
    "9000:MinIO（オブジェクトストレージ）"
)

# 各ポートをチェック
for PORT_INFO in "${PORTS[@]}"; do
    PORT=$(echo $PORT_INFO | cut -d: -f1)
    DESC=$(echo $PORT_INFO | cut -d: -f2-)

    # ポート使用状況を確認
    if lsof -i :$PORT > /dev/null 2>&1; then
        echo "❌ ポート $PORT ($DESC) は使用中:"
        lsof -i :$PORT | grep LISTEN | head -1

        # プロセス詳細を取得
        PID=$(lsof -ti :$PORT | head -1)
        if [ ! -z "$PID" ]; then
            PROCESS=$(ps -p $PID -o comm= 2>/dev/null)
            echo "   プロセス: $PROCESS (PID: $PID)"
        fi
    else
        echo "✅ ポート $PORT ($DESC) は利用可能"
    fi
    echo
done

# 推奨事項
echo "=== 推奨事項 ==="
echo "1. 各セッションは割り当てられたポートを使用してください："
echo "   - UI Session: 5173"
echo "   - API Session: 5174"
echo "   - Camera Session: 5175"
echo "   - AI Session: 5176"
echo "   - Deploy Session: 5177"
echo
echo "2. ポートを変更するには："
echo "   npm run dev -- --port 5174"
echo "   または vite.config.ts で設定"
echo
echo "3. 使用中のポートを解放するには："
echo "   kill -9 <PID>"
