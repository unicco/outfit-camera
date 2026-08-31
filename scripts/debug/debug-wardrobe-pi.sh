#!/bin/bash

# Raspberry Pi でのワードローブ画像表示問題デバッグ（本番環境用）
# SSH で実行: curl -s https://raw.githubusercontent.com/[repo]/debug-wardrobe-pi.sh | bash

echo "🔍 ワードローブ画像表示問題の診断を開始"
echo "========================================"

# 基本的な接続確認
echo "1. API サーバー接続確認"
if curl -f "http://localhost:8000/health" > /dev/null 2>&1; then
    echo "✅ API サーバーが稼働中"
else
    echo "❌ API サーバーに接続できません"
    echo "   解決方法: ./scripts/start-development.sh を実行してサービスを起動"
    exit 1
fi

# ワードローブエンドポイント確認
echo ""
echo "2. ワードローブ API エンドポイント確認"
if curl -f "http://localhost:8000/api/v2/wardrobe/items" > /dev/null 2>&1; then
    echo "✅ ワードローブ API が応答"

    # サンプルアイテム取得
    echo "   サンプルアイテム確認中..."
    SAMPLE_DATA=$(curl -s "http://localhost:8000/api/v2/wardrobe/items" | jq -r '.[0] | "\(.id): \(.image_urls[0] // "no images")"' 2>/dev/null || echo "jq not available")
    echo "   レスポンス例: ${SAMPLE_DATA}"
else
    echo "❌ ワードローブ API にアクセスできません"
fi

# 画像ファイル確認
echo ""
echo "3. 画像ファイル存在確認"
WARDROBE_DIR="$HOME/coordinate-recorder/api/v2/wardrobe_images"
if [ -d "$WARDROBE_DIR" ]; then
    echo "✅ ワードローブ画像ディレクトリが存在: $WARDROBE_DIR"

    # ファイル数確認
    IMAGE_COUNT=$(find "$WARDROBE_DIR" -name "*.jpg" | wc -l)
    echo "   画像ファイル数: $IMAGE_COUNT"

    # サンプル画像確認
    SAMPLE_IMAGE=$(find "$WARDROBE_DIR" -name "*.jpg" | head -1)
    if [ -n "$SAMPLE_IMAGE" ]; then
        echo "   サンプル画像: $SAMPLE_IMAGE"

        # ファイル権限確認
        ls -la "$SAMPLE_IMAGE"

        # 画像URLテスト
        RELATIVE_PATH=${SAMPLE_IMAGE#$WARDROBE_DIR}
        IMAGE_URL="http://localhost:8000/static/wardrobe${RELATIVE_PATH}"
        echo "   テストURL: $IMAGE_URL"

        if curl -f "$IMAGE_URL" -I > /dev/null 2>&1; then
            echo "✅ 画像 URL アクセス成功"
        else
            echo "❌ 画像 URL アクセス失敗"
            echo "   HTTP ステータス:"
            curl -I "$IMAGE_URL" 2>&1 | head -3
        fi
    else
        echo "   ⚠️ 画像ファイルが見つかりません"
    fi
else
    echo "❌ ワードローブ画像ディレクトリが見つかりません: $WARDROBE_DIR"
    echo "   代替パス確認:"
    find /home/pi -name "wardrobe_images" -type d 2>/dev/null || echo "   見つかりませんでした"
fi

# Environment Variables 確認
echo ""
echo "4. 環境変数確認"
echo "   STORAGE_TYPE: ${STORAGE_TYPE:-'未設定'}"
echo "   GCS_BUCKET_NAME: ${GCS_BUCKET_NAME:-'未設定'}"

# サービスプロセス確認
echo ""
echo "5. サービス状況確認"
echo "   API サーバープロセス:"
ps aux | grep -E "(uvicorn|python.*main)" | grep -v grep | head -2 || echo "   APIプロセスが見つかりません"

echo ""
echo "   UI サーバープロセス:"
ps aux | grep -E "(node.*dev|vite)" | grep -v grep | head -2 || echo "   UIプロセスが見つかりません"

# 推奨解決手順
echo ""
echo "🔧 推奨解決手順"
echo "=================="
echo "1. サービス再起動:"
echo "   cd /home/pi/coordinate-recorder"
echo "   ./scripts/stop-development.sh"
echo "   ./scripts/start-development.sh"
echo ""
echo "2. 権限修正 (必要な場合):"
echo "   sudo chown -R unicco:unicco /home/pi/coordinate-recorder/api/v2/wardrobe_images"
echo "   chmod -R 755 /home/pi/coordinate-recorder/api/v2/wardrobe_images"
echo ""
echo "3. ブラウザでワードローブページを開く:"
echo "   http://pi-camera.local:3000"
echo ""
echo "🔍 診断完了"
