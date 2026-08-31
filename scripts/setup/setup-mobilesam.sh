#!/bin/bash
# MobileSAM セットアップスクリプト

set -e

echo "=== MobileSAM セットアップ ==="
echo ""

# スクリプトのディレクトリを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "📦 PyTorch のインストール..."
# CPU 版の PyTorch をインストール（Raspberry Pi 対応）
if [[ $(uname -m) == "aarch64" ]]; then
    # ARM64 (Raspberry Pi) 向け
    echo "ARM64 アーキテクチャを検出しました"
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
else
    # x86_64 向け
    echo "x86_64 アーキテクチャを検出しました"
    pip install torch torchvision
fi

echo ""
echo "📦 gdown のインストール（Google Drive ダウンロード用）..."
pip install gdown

echo ""
echo "📦 timm のインストール（MobileSAM の依存関係）..."
pip install timm

echo ""
echo "📦 MobileSAM のインストール..."
pip install git+https://github.com/ChaoningZhang/MobileSAM.git

echo ""
echo "📥 MobileSAM モデルのダウンロード..."
python "$SCRIPT_DIR/download_mobilesam_model.py"

echo ""
echo "🔍 インストール確認..."
python -c "
import torch
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"CPU\"}')

try:
    from mobile_sam import sam_model_registry
    print('✅ MobileSAM インポート成功')
except ImportError as e:
    print(f'❌ MobileSAM インポート失敗: {e}')
"

echo ""
echo "✅ MobileSAM セットアップ完了！"
echo ""
echo "使用方法："
echo "  python tests/test_segmentation_comparison.py"