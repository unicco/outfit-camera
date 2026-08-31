#!/usr/bin/env python3
"""クロップ画像実装の効果をテスト."""

import requests


def test_ai_detection_with_crops():
    print("🔍 クロップ画像実装効果のテスト")

    # AI検出APIを呼び出し
    url = "http://localhost:8014/api/v2/ai/detect"
    payload = {
        "photo_id": "20250726_160011_19",
        "crop_items": True,
        "match_wardrobe": True,
        "annotate_image": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()

        print(f"✅ 検出成功: {result['detection_count']}個のアイテム")

        for i, item in enumerate(result.get("detected_items", [])):
            print(f"\n📷 アイテム {i + 1}: {item['category']}")
            print(f"   信頼度: {item['confidence']:.2f}")
            print(f"   クロップ画像: {item.get('cropped_image_url', 'なし')[:50]}...")

            # トップ3のマッチング候補
            candidates = item.get("wardrobe_match_candidates", [])[:3]
            if candidates:
                print("   📊 トップ3マッチング結果:")
                for j, candidate in enumerate(candidates, 1):
                    similarity = candidate.get("similarity_score") or candidate.get(
                        "match_score", 0
                    )
                    print(
                        f"     {j}位: {similarity:.1%} ({candidate.get('match_reason', '不明')})"
                    )
            else:
                print("   ❌ マッチング候補なし")

        # 正解シャツが含まれているかチェック
        correct_shirt_id = "796010f3-2f62-4b60-84c3-19790913550d"
        found_correct = False

        for item in result.get("detected_items", []):
            for candidate in item.get("wardrobe_match_candidates", []):
                if candidate.get("item_id") == correct_shirt_id:
                    similarity = candidate.get("similarity_score") or candidate.get(
                        "match_score", 0
                    )
                    print("\n🎯 正解シャツ発見！")
                    print(f"   類似度: {similarity:.1%}")
                    print(f"   アルゴリズム: {candidate.get('match_reason', '不明')}")
                    found_correct = True
                    break

        if not found_correct:
            print("\n❌ 正解シャツが見つかりませんでした")
            print(f"   expected ID: {correct_shirt_id}")

    except requests.exceptions.RequestException as e:
        print(f"❌ API呼び出し失敗: {e}")
    except Exception as e:
        print(f"❌ エラー: {e}")


if __name__ == "__main__":
    test_ai_detection_with_crops()
