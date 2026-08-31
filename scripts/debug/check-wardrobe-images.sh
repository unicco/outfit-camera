#!/bin/bash

# Raspberry Pi でのワードローブ画像表示問題デバッグスクリプト
# 使用方法: ./scripts/debug/check-wardrobe-images.sh

echo "🔍 ワードローブ画像表示問題の診断を開始"
echo "========================================"

# 基本的な接続確認
echo "1. API サーバー接続確認"
API_URL="http://pi-camera.local:8000"
if curl -f "${API_URL}/health" > /dev/null 2>&1; then
    echo "✅ API サーバーが稼働中"
else
    echo "❌ API サーバーに接続できません"
    echo "   解決方法: ./scripts/start-dev.sh を実行してサービスを起動"
    exit 1
fi

# ワードローブエンドポイント確認
echo ""
echo "2. ワードローブ API エンドポイント確認"
if curl -f "${API_URL}/api/v2/wardrobe/items" > /dev/null 2>&1; then
    echo "✅ ワードローブ API が応答"

    # サンプルアイテム取得
    echo "   サンプルアイテム確認中..."
    SAMPLE_DATA=$(curl -s "${API_URL}/api/v2/wardrobe/items" | head -c 500)
    echo "   レスポンス例: ${SAMPLE_DATA}..."
else
    echo "❌ ワードローブ API にアクセスできません"
fi

# 画像ファイル確認
echo ""
echo "3. 画像ファイル存在確認"
WARDROBE_DIR="/home/pi/coordinate-recorder/api/v2/wardrobe_images"
if [ -d "$WARDROBE_DIR" ]; then
    echo "✅ ワードローブ画像ディレクトリが存在: $WARDROBE_DIR"

    # ファイル数確認
    IMAGE_COUNT=$(find "$WARDROBE_DIR" -name "*.jpg" | wc -l)
    echo "   画像ファイル数: $IMAGE_COUNT"

    # サンプル画像確認
    SAMPLE_IMAGE=$(find "$WARDROBE_DIR" -name "*.jpg" | head -1)
    if [ -n "$SAMPLE_IMAGE" ]; then
        echo "   サンプル画像: $SAMPLE_IMAGE"

        # 画像URLテスト
        RELATIVE_PATH=${SAMPLE_IMAGE#$WARDROBE_DIR}
        IMAGE_URL="${API_URL}/static/wardrobe${RELATIVE_PATH}"
        echo "   テストURL: $IMAGE_URL"

        if curl -f "$IMAGE_URL" -I > /dev/null 2>&1; then
            echo "✅ 画像 URL アクセス成功"
        else
            echo "❌ 画像 URL アクセス失敗"
            echo "   確認事項:"
            echo "   - Static Files Mount 設定"
            echo "   - ファイル権限"
            echo "   - パス構造"
        fi
    fi
else
    echo "❌ ワードローブ画像ディレクトリが見つかりません: $WARDROBE_DIR"
fi

# UI サーバー確認
echo ""
echo "4. UI サーバー確認"
UI_URL="http://pi-camera.local:3000"
if curl -f "$UI_URL" > /dev/null 2>&1; then
    echo "✅ UI サーバーが稼働中"
else
    echo "❌ UI サーバーに接続できません"
fi

# 推奨解決手順
echo ""
echo "🔧 推奨解決手順"
echo "=================="
echo "1. サービス再起動:"
echo "   cd /home/pi/coordinate-recorder"
echo "   ./scripts/stop-development.sh"
echo "   ./scripts/start-dev.sh"
echo ""
echo "2. ブラウザでワードローブページを開く:"
echo "   http://pi-camera.local:3000"
echo ""
echo "3. ブラウザの開発者ツールで確認:"
echo "   - Console: JavaScript エラー"
echo "   - Network: 画像リクエストの応答コード"
echo "   - Generated URLs の確認"
echo ""
echo "4. 必要に応じて権限修正:"
echo "   sudo chown -R unicco:unicco /home/pi/coordinate-recorder/api/v2/wardrobe_images"
echo "   chmod -R 755 /home/pi/coordinate-recorder/api/v2/wardrobe_images"

echo ""
echo "🔍 診断完了"
