#!/usr/bin/env python3
"""GCS画像表示の手動確認スクリプト（pytest テストではない）.

実 GCS と実サービスアカウント鍵を直接叩く手動デバッグ用。実行前に鍵パスを
export しておくこと（で integration から移設）:

    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/gcs-service-account-key.json
    export GCS_BUCKET_NAME=example-wardrobe-dev   # 省略時はこの値
    python scripts/manual/gcs_images_check.py

下の photo_id は各自の環境に合わせて書き換えること。
"""

import os
import sys

import requests
from google.cloud import storage

# 鍵パスは環境変数から取得（個人パスはハードコードしない）
if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    sys.exit("GOOGLE_APPLICATION_CREDENTIALS を export してから実行してください")
os.environ.setdefault("GCS_BUCKET_NAME", "example-wardrobe-dev")
os.environ.setdefault("STORAGE_TYPE", "gcs")


def test_gcs_direct_access():
    """GCSへの直接アクセステスト."""
    print("=== GCS直接アクセステスト ===")

    client = storage.Client()
    bucket = client.bucket("example-wardrobe-dev")

    # アップロードされた画像ファイルを確認
    photo_ids = [
        "8f1563bd-2ccb-4c11-8034-5f6673d04d52",
        "0aa30bbe-db92-4063-a4cd-dab9f12d3698",
        "4a8195a6-1237-4db5-9d1b-84fad9448607",
    ]

    for photo_id in photo_ids:
        blob_name = f"photos/{photo_id}.jpg"
        gcs_url = f"https://storage.googleapis.com/example-wardrobe-dev/{blob_name}"

        try:
            blob = bucket.blob(blob_name)
            blob.reload()
            print(f"✅ GCS画像確認: {photo_id}")
            print(f"   サイズ: {blob.size:,} bytes")
            print(f"   URL: {gcs_url}")
        except Exception as e:
            print(f"❌ GCS画像エラー: {photo_id} - {e}")
        print()


def test_api_photo_endpoints():
    """API画像エンドポイントのテスト."""
    print("=== API画像エンドポイントテスト ===")

    # テスト対象の画像ID
    photo_ids = [
        "8f1563bd-2ccb-4c11-8034-5f6673d04d52",
        "0aa30bbe-db92-4063-a4cd-dab9f12d3698",
        "4a8195a6-1237-4db5-9d1b-84fad9448607",
    ]

    api_base = "http://localhost:8000"

    for photo_id in photo_ids:
        # メインエンドポイント
        main_url = f"{api_base}/photos/{photo_id}"
        v2_url = f"{api_base}/v2/photos/{photo_id}"

        print(f"🔍 テスト画像ID: {photo_id}")

        # メインエンドポイントテスト
        try:
            response = requests.head(main_url, timeout=10)
            if response.status_code == 200:
                print(f"✅ メインエンドポイント: {main_url}")
                print(f"   Content-Type: {response.headers.get('content-type')}")
            elif response.status_code == 302:
                redirect_url = response.headers.get("location", "Unknown")
                print(f"🔄 メインエンドポイント（リダイレクト）: {main_url}")
                print(f"   リダイレクト先: {redirect_url}")
            else:
                print(f"❌ メインエンドポイント: {main_url} - {response.status_code}")
        except Exception as e:
            print(f"❌ メインエンドポイントエラー: {e}")

        # V2エンドポイントテスト
        try:
            response = requests.head(v2_url, timeout=10)
            if response.status_code == 200:
                print(f"✅ V2エンドポイント: {v2_url}")
                print(f"   Content-Type: {response.headers.get('content-type')}")
            elif response.status_code == 302:
                redirect_url = response.headers.get("location", "Unknown")
                print(f"🔄 V2エンドポイント（リダイレクト）: {v2_url}")
                print(f"   リダイレクト先: {redirect_url}")
            else:
                print(f"❌ V2エンドポイント: {v2_url} - {response.status_code}")
        except Exception as e:
            print(f"❌ V2エンドポイントエラー: {e}")

        print()


def test_records_endpoint():
    """レコードエンドポイントのテスト."""
    print("=== レコードエンドポイントテスト ===")

    try:
        response = requests.get("http://localhost:8000/v2/records", timeout=10)
        if response.status_code == 200:
            records = response.json()
            print("✅ レコードエンドポイント成功")
            print(f"   レコード数: {len(records.get('records', []))}")

            # 最初のレコードの画像URLを確認
            if records.get("records"):
                first_record = records["records"][0]
                photo_url = first_record.get("photo_url", "N/A")
                print(f"   最初のレコードの画像URL: {photo_url}")
        else:
            print(f"❌ レコードエンドポイント: {response.status_code}")
    except Exception as e:
        print(f"❌ レコードエンドポイントエラー: {e}")


if __name__ == "__main__":
    print("🧪 GCS画像表示テスト開始")
    print("=" * 50)

    test_gcs_direct_access()
    test_api_photo_endpoints()
    test_records_endpoint()

    print("=" * 50)
    print("🎉 テスト完了")
