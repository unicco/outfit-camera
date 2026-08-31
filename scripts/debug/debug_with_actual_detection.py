#!/usr/bin/env python3
"""Test task optimization with actual AI detection results."""

import os
import sys

import requests

api_path = "./api"
sys.path.insert(0, api_path)
sys.path.insert(0, "./src")
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://coordinate_user:coordinate_pass@localhost:5438/coordinate_db"
)


def test_actual_ai_detection():
    """Test with actual AI detection API call."""
    print("🧪 実際の AI 検出を使用したテスト")
    print("=" * 50)

    # Use a known test photo ID (from previous tests)
    # In a real scenario, you would get this from the database
    photo_id = (
        "test-photo-001"  # Placeholder - replace with actual photo ID if available
    )
    print(f"📸 使用する写真ID: {photo_id} (テスト用)")

    # Make AI detection API call
    print("\n🤖 AI 検出 API 呼び出し")

    api_url = "http://localhost:8014/api/v2/ai/detect"

    request_data = {
        "photo_id": photo_id,
        "crop_items": True,
        "match_wardrobe": True,
        "annotate_image": True,
    }

    try:
        response = requests.post(
            api_url,
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )

        if not response.ok:
            print(f"❌ API エラー: {response.status_code} {response.text}")
            return

        result = response.json()

        print(f"✅ AI 検出成功: {result['detection_count']}個のアイテムを検出")
        print(f"   処理時間: {result['processing_time_ms']:.0f}ms")

        # Analyze detected items
        for i, item in enumerate(result["detected_items"], 1):
            print(f"\n📋 検出アイテム {i}: {item['category']}")
            print(f"   信頼度: {item['confidence'] * 100:.1f}%")
            print(f"   主要色: {item.get('color_primary', '不明')}")
            print(f"   クロップ画像: {'✅' if item.get('cropped_image_url') else '❌'}")

            # Check wardrobe matches
            matches = item.get("wardrobe_match_candidates", [])
            print(f"   ワードローブマッチ: {len(matches)}件")

            if matches:
                print("   上位3件:")
                for j, match in enumerate(matches[:3], 1):
                    similarity = match.get(
                        "similarity_score", match.get("match_score", 0)
                    )
                    print(f"     {j}. {match['name']} ({similarity * 100:.1f}%)")

                # Check if correct shirt is in matches
                correct_shirt_id = "796010f3-2f62-4b60-84c3-19790913550d"
                correct_found = False

                for j, match in enumerate(matches, 1):
                    if match["item_id"] == correct_shirt_id:
                        correct_found = True
                        similarity = match.get(
                            "similarity_score", match.get("match_score", 0)
                        )
                        print(f"   🎯 正解シャツ発見: {j}位 ({similarity * 100:.1f}%)")
                        break

                if not correct_found:
                    print(f"   ❌ 正解シャツが見つかりません（全{len(matches)}件中）")

            print(
                f"   マッチ理由: {matches[0]['match_reason'] if matches else 'マッチなし'}"
            )

        # Check if using jina_embedding or traditional_algorithm
        detected_method = "不明"
        if result["detected_items"]:
            first_item = result["detected_items"][0]
            if first_item.get("wardrobe_match_candidates"):
                first_match = first_item["wardrobe_match_candidates"][0]
                if "similarity_score" in first_match:
                    detected_method = "jina_embedding (最適化済)"
                elif "match_score" in first_match:
                    detected_method = "traditional_algorithm"

        print(f"\n🔧 使用されたマッチング手法: {detected_method}")

        return result

    except Exception as e:
        print(f"❌ API 呼び出しエラー: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_actual_ai_detection()
