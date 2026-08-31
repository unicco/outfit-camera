#!/usr/bin/env python3
"""MobileSAM モデルの互換性チェック."""

import os
import pickle
import torch


def check_model_file(model_path):
    """モデルファイルの形式を確認."""
    print(f"モデルファイル: {model_path}")
    print(f"ファイルサイズ: {os.path.getsize(model_path) / 1e9:.2f} GB")

    # ファイルの最初のバイトを確認
    with open(model_path, "rb") as f:
        # PyTorch モデルのマジックナンバーを確認
        magic = f.read(10)
        print(f"マジックナンバー: {magic}")

        # ZIP ファイル（新しい PyTorch 形式）かどうか
        f.seek(0)
        if f.read(2) == b"PK":
            print("形式: ZIP アーカイブ (PyTorch 1.6+ 形式)")

            # ZIP の内容を確認
            import zipfile

            with zipfile.ZipFile(model_path, "r") as zf:
                print("ZIP 内のファイル:")
                for name in zf.namelist()[:10]:  # 最初の10個
                    print(f"  - {name}")
        else:
            print("形式: レガシー形式またはカスタム形式")

    print("\n=== ロード試行 ===")

    # 方法1: pickle で直接読み込み
    try:
        with open(model_path, "rb") as f:
            data = pickle.load(f)
        print("✅ pickle.load 成功")
        print(f"データタイプ: {type(data)}")
    except Exception as e:
        print(f"❌ pickle.load 失敗: {e}")

    # 方法2: torch.load with map_location
    try:
        data = torch.load(model_path, map_location="cpu", weights_only=True)
        print("✅ torch.load (weights_only=True) 成功")
    except Exception as e:
        print(f"❌ torch.load (weights_only=True) 失敗: {e}")

    # 方法3: unsafe load
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            data = torch.load(model_path, map_location="cpu", pickle_module=pickle)
        print("✅ torch.load (pickle_module) 成功")

        if isinstance(data, dict):
            print(f"辞書のキー: {list(data.keys())[:5]}")
    except Exception as e:
        print(f"❌ torch.load (pickle_module) 失敗: {e}")


if __name__ == "__main__":
    model_path = os.path.expanduser("~/.cache/mobilesam/mobile_sam.pt")

    if not os.path.exists(model_path):
        print(f"モデルファイルが見つかりません: {model_path}")
    else:
        check_model_file(model_path)
