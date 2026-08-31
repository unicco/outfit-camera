#!/usr/bin/env python3
"""UIに残っているデータを確認するスクリプト."""

import json

import requests


def check_api_endpoints() -> None:
    """API エンドポイントの確認."""
    print("🔍 API エンドポイント確認")
    print("=" * 50)

    api_base = "http://localhost:8000"

    endpoints_to_check = [
        "/api/v2/records",
        "/api/v2/photos",
        "/debug/photos",
        "/api/v2/outfits/all",
    ]

    for endpoint in endpoints_to_check:
        url = f"{api_base}{endpoint}"
        try:
            response = requests.get(url, timeout=10)
            print(f"\n📡 {endpoint}")
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        if "records" in data:
                            records = data["records"]
                            print(f"   レコード数: {len(records)}")
                            if records:
                                print("   最初のレコード:")
                                first_record = records[0]
                                for key, value in first_record.items():
                                    print(f"     {key}: {value}")
                        elif "photos" in data:
                            photos = data["photos"]
                            print(f"   写真数: {len(photos)}")
                        else:
                            print(f"   データキー: {list(data.keys())}")
                            if len(data) > 0:
                                print(f"   データ件数: {len(data)}")
                    elif isinstance(data, list):
                        print(f"   リスト件数: {len(data)}")
                        if data:
                            print("   最初の要素:")
                            print(f"     {data[0]}")
                    else:
                        print(f"   データ型: {type(data)}")
                        print(f"   内容: {str(data)[:200]}...")

                except json.JSONDecodeError:
                    print(f"   テキスト応答: {response.text[:200]}...")
            else:
                print(f"   エラー: {response.text[:200]}...")

        except Exception as e:
            print(f"   例外: {e}")


def check_ui_data_sources() -> None:
    """UIが参照する可能性のあるデータソースを確認."""
    print("\n\n🎯 UIデータソース分析")
    print("=" * 50)

    # UIが使用する主要エンドポイント
    response = requests.get("http://localhost:8000/api/v2/records", timeout=10)

    if response.status_code == 200:
        data = response.json()
        records = data.get("records", [])

        print("UIメインデータソース (/api/v2/records):")
        print(f"  レコード数: {len(records)}")

        if records:
            print("\n詳細レコード情報:")
            for i, record in enumerate(records):
                print(f"\n  レコード {i + 1}:")
                for key, value in record.items():
                    print(f"    {key}: {value}")

                # 画像URLが存在する場合、実際にアクセスしてみる
                if "photo_url" in record:
                    photo_url = record["photo_url"]
                    try:
                        photo_response = requests.head(photo_url, timeout=5)
                        print(f"    画像アクセス: {photo_response.status_code}")
                        if photo_response.status_code == 302:
                            redirect_url = photo_response.headers.get("location")
                            print(f"    リダイレクト先: {redirect_url}")
                    except Exception as e:
                        print(f"    画像アクセスエラー: {e}")
    else:
        print(f"エラー: {response.status_code} - {response.text[:200]}")


if __name__ == "__main__":
    print("🔍 UI残存データ調査開始")

    check_api_endpoints()
    check_ui_data_sources()

    print("\n" + "=" * 50)
    print("🎉 調査完了")
