#!/bin/bash

# Tailscale 期限切れデバイス手動クリーンアップスクリプト
# 使用法: ./scripts/maintenance/cleanup-tailscale-devices.sh

set -e

echo "🔍 Tailscale 期限切れデバイスクリーンアップ"
echo ""

# 必要な環境変数をチェック
if [ -z "$TS_OAUTH_CLIENT_ID" ] || [ -z "$TS_OAUTH_SECRET" ] || [ -z "$TS_TAILNET" ]; then
    echo "⚠️ 環境変数が設定されていません:"
    echo "export TS_OAUTH_CLIENT_ID='your-oauth-client-id'"
    echo "export TS_OAUTH_SECRET='your-oauth-secret'"
    echo "export TS_TAILNET='your-tailnet-id'"
    echo ""
    echo "Tailscale OAuth Client を作成してください:"
    echo "https://login.tailscale.com/admin/settings/oauth"
    echo ""
    echo "必要な権限: devices:read, devices:write"
    exit 1
fi

echo "🔑 OAuth トークンを取得中..."

# OAuth トークンを取得
TOKEN_RESPONSE=$(curl -s -d "client_id=$TS_OAUTH_CLIENT_ID" \
    -d "client_secret=$TS_OAUTH_SECRET" \
    -d "grant_type=client_credentials" \
    -d "scope=devices" \
    "https://api.tailscale.com/api/v2/oauth/token")

if [ $? -ne 0 ]; then
    echo "❌ OAuth トークンの取得に失敗しました"
    exit 1
fi

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')

if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ OAuth トークンが無効です"
    echo "Response: $TOKEN_RESPONSE"
    exit 1
fi

echo "📋 デバイス一覧を取得中..."

# デバイス一覧を取得
DEVICES=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
    "https://api.tailscale.com/api/v2/tailnet/$TS_TAILNET/devices")

if [ $? -ne 0 ]; then
    echo "❌ Tailscale API へのアクセスに失敗しました"
    exit 1
fi

# GitHub Actions 関連の期限切れデバイスを表示
echo "🔍 GitHub Actions 関連の期限切れデバイス:"
echo "$DEVICES" | jq -r '.devices[] | select(.name | test("github-")) | select(.keyExpiryDisabled == false) | select(.expires != null) | select(.expires < now) | "\(.name) (\(.id)) - Expired: \(.expires)"'

EXPIRED_COUNT=$(echo "$DEVICES" | jq -r '.devices[] | select(.name | test("github-")) | select(.keyExpiryDisabled == false) | select(.expires != null) | select(.expires < now) | .id' | wc -l)

echo ""
echo "📊 期限切れデバイス数: $EXPIRED_COUNT"

if [ "$EXPIRED_COUNT" -eq 0 ]; then
    echo "✅ 期限切れデバイスはありません"
    exit 0
fi

echo ""
read -p "🗑️ これらのデバイスを削除しますか？ (y/N): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🧹 削除を開始します..."

    # 期限切れデバイスを削除
    echo "$DEVICES" | jq -r '.devices[] | select(.name | test("github-")) | select(.keyExpiryDisabled == false) | select(.expires != null) | select(.expires < now) | .id' | while read -r device_id; do
        if [ -n "$device_id" ]; then
            echo "🗑️ 削除中: $device_id"
            curl -s -X DELETE \
                -H "Authorization: Bearer $ACCESS_TOKEN" \
                "https://api.tailscale.com/api/v2/device/$device_id"

            if [ $? -eq 0 ]; then
                echo "✅ 削除完了: $device_id"
            else
                echo "❌ 削除失敗: $device_id"
            fi
        fi
    done

    echo ""
    echo "🎉 クリーンアップ完了！"
else
    echo "❌ キャンセルしました"
fi
