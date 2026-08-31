#!/bin/bash
# MobileSAM Lite セットアップ（開発・テスト用の軽量版）

set -e

echo "=== MobileSAM Lite セットアップ ==="
echo ""
echo "⚠️  注意: 本番用の完全なモデルではなく、開発・テスト用の設定です"
echo ""

# スクリプトのディレクトリを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# MobileSAM がインストールされているか確認
if python -c "import mobile_sam" 2>/dev/null; then
    echo "✅ MobileSAM パッケージは既にインストールされています"
else
    echo "📦 MobileSAM のインストール..."
    pip install git+https://github.com/ChaoningZhang/MobileSAM.git
fi

# ダミーモデルファイルを作成（テスト用）
echo ""
echo "📝 テスト用ダミーモデルを作成..."
mkdir -p ~/.cache/mobilesam

python << EOF
import torch
import os

# ダミーの state_dict を作成（最小限の構造）
dummy_state = {
    'image_encoder.patch_embed.proj.weight': torch.randn(192, 3, 4, 4),
    'image_encoder.patch_embed.proj.bias': torch.randn(192),
    'mask_decoder.iou_token.weight': torch.randn(1, 1, 256),
    'prompt_encoder.point_embeddings.0.weight': torch.randn(1, 1, 256),
}

# 保存
model_path = os.path.expanduser('~/.cache/mobilesam/mobile_sam_dummy.pt')
torch.save(dummy_state, model_path)
print(f"✅ ダミーモデルを保存: {model_path}")
EOF

echo ""
echo "📝 MobileSAM 設定ファイルを更新..."
cat > ~/.cache/mobilesam/config.json << EOF
{
  "model_type": "dummy",
  "model_path": "~/.cache/mobilesam/mobile_sam_dummy.pt",
  "fallback_to_grabcut": true,
  "warning": "This is a dummy model for testing. Real segmentation will use GrabCut fallback."
}
EOF

echo ""
echo "✅ セットアップ完了！"
echo ""
echo "⚠️  重要: これはテスト用のダミー設定です。"
echo "実際のセグメンテーションは GrabCut にフォールバックされます。"
echo ""
echo "完全なモデルをダウンロードするには："
echo "1. Google Drive から手動でダウンロード"
echo "2. または VPN 経由で Hugging Face からダウンロード"
echo ""