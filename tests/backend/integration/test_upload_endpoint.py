#!/usr/bin/env python3
"""/api/v2/upload エンドポイントのテストスクリプト."""

import io

import numpy as np
import requests
from PIL import Image


# テスト画像を生成
def create_test_image():
    # 640x480 のテスト画像を作成
    img_array = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    img = Image.fromarray(img_array)

    # バイトストリームに変換
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_byte_arr.seek(0)

    return img_byte_arr


# エンドポイントをテスト
def test_upload_endpoint():
    url = "http://localhost:8000/api/v2/upload"

    # テスト画像を作成
    test_image = create_test_image()

    # ファイルとして送信
    files = {"file": ("test_photo.jpg", test_image, "image/jpeg")}

    try:
        response = requests.post(url, files=files)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code == 200:
            print("✅ Upload successful!")
            result = response.json()
            print(f"  - Photo ID: {result['id']}")
            print(f"  - URL: {result['url']}")
            print(f"  - Filename: {result['filename']}")
            print(f"  - Timestamp: {result['timestamp']}")
        else:
            print("❌ Upload failed!")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("Testing /api/v2/upload endpoint...")
    test_upload_endpoint()
