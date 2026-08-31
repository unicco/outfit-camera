#!/usr/bin/env python3
"""Few-shot 学習システムのテストスクリプト."""

import os
import sys

import requests

# API のベース URL
API_BASE = os.getenv("API_URL", "http://localhost:8000")


def test_annotation_list(user_id="test_user"):
    """アノテーション一覧取得テスト."""
    print(f"\n1. アノテーション一覧取得 (user_id: {user_id})")
    response = requests.get(f"{API_BASE}/api/v2/few-shot/annotations/{user_id}")
    if response.ok:
        data = response.json()
        print(f"✓ 成功: {data['total']} 件のアノテーション")
        return data["annotations"]
    else:
        print(f"✗ 失敗: {response.status_code} - {response.text}")
        return []


def test_training(user_id="test_user"):
    """学習実行テスト."""
    print(f"\n2. モデル学習 (user_id: {user_id})")
    payload = {"user_id": user_id, "n_epochs": 5, "learning_rate": 0.001}
    response = requests.post(f"{API_BASE}/api/v2/few-shot/train", json=payload)
    if response.ok:
        data = response.json()
        print(f"✓ 成功: {data['n_training_images']} 枚で学習完了")
        print(f"  最終損失: {data['final_loss']:.4f}")
        return True
    else:
        print(f"✗ 失敗: {response.status_code} - {response.text}")
        return False


def test_prediction(user_id="test_user", image_path=None):
    """予測テスト."""
    print(f"\n3. レイヤー予測 (user_id: {user_id})")

    if not image_path:
        # ダミー画像を使用
        print("  (ダミー画像でテスト)")
        import numpy as np
        from PIL import Image
        import io

        # 640x480 のダミー画像作成
        img_array = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        img = Image.fromarray(img_array)

        # バイトストリームに変換
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        files = {"image_file": ("test.jpg", img_bytes, "image/jpeg")}
    else:
        with open(image_path, "rb") as f:
            files = {"image_file": f}

    data = {"user_id": user_id}
    response = requests.post(f"{API_BASE}/api/v2/few-shot/predict", files=files, data=data)

    if response.ok:
        result = response.json()
        print(f"✓ 成功: {len(result['layers'])} 個のレイヤーを検出")
        print(f"  処理時間: {result['processing_time']:.2f}秒")
        for layer in result["layers"]:
            print(f"  - {layer['layer_type']}: 信頼度 {layer['confidence']:.2f}")
        return True
    else:
        print(f"✗ 失敗: {response.status_code} - {response.text}")
        return False


def main():
    """メインテスト実行."""
    print("Few-shot 学習システムのテスト")
    print("=" * 50)

    # API ヘルスチェック
    try:
        response = requests.get(f"{API_BASE}/health")
        if not response.ok:
            print("✗ API サーバーが起動していません")
            sys.exit(1)
    except requests.ConnectionError:
        print("✗ API サーバーに接続できません")
        print("  ./scripts/start-development.sh を実行してください")
        sys.exit(1)

    user_id = "test_user"

    # テスト実行
    annotations = test_annotation_list(user_id)

    if len(annotations) >= 3:
        # 学習実行
        if test_training(user_id):
            # 予測テスト
            test_prediction(user_id)
    else:
        print(
            f"\n⚠️  学習には最低3枚のアノテーションが必要です（現在: {len(annotations)}枚）"
        )
        print("   UI でアノテーションを追加してください")

    print("\n" + "=" * 50)
    print("テスト完了")


if __name__ == "__main__":
    main()
