#!/usr/bin/env python3
"""アイテムタイプ検出システムのデモスクリプト."""

import requests

API_BASE = "http://localhost:8032"
USER_ID = "demo-user"


def main():
    print("=== アイテムタイプ検出システムのデモ ===\n")

    # 1. サポートされるタイプを確認
    print("1. サポートされるアイテムタイプ:")
    response = requests.get(f"{API_BASE}/api/v2/few-shot/item-type/supported-types")
    if response.status_code == 200:
        data = response.json()
        for item_type, description in data["descriptions"].items():
            print(f"   - {item_type}: {description}")
    print()

    # 2. 現在の統計情報
    print("2. 現在の学習状況:")
    response = requests.get(f"{API_BASE}/api/v2/few-shot/item-type/statistics/{USER_ID}")
    if response.status_code == 200:
        stats = response.json()["statistics"]
        print(f"   - 総アノテーション数: {stats['total_annotations']}")
        print(f"   - 学習済: {'はい' if stats['is_trained'] else 'いいえ'}")
        if stats["type_distribution"]:
            print("   - タイプ別アノテーション数:")
            for item_type, count in stats["type_distribution"].items():
                print(f"     - {item_type}: {count}")
    print()

    # 3. テスト用アノテーションを追加
    print("3. テスト用アノテーションを追加:")
    test_annotations = [
        {
            "item_type": "dress",
            "image": "dress1.jpg",
            "bbox": [[10, 10], [200, 10], [200, 300], [10, 300]],
        },
        {
            "item_type": "dress",
            "image": "dress2.jpg",
            "bbox": [[20, 20], [180, 20], [180, 280], [20, 280]],
        },
        {
            "item_type": "dress",
            "image": "dress3.jpg",
            "bbox": [[15, 15], [190, 15], [190, 290], [15, 290]],
        },
        {
            "item_type": "tops",
            "image": "shirt1.jpg",
            "bbox": [[30, 30], [170, 30], [170, 150], [30, 150]],
        },
        {
            "item_type": "tops",
            "image": "shirt2.jpg",
            "bbox": [[25, 25], [175, 25], [175, 145], [25, 145]],
        },
        {
            "item_type": "tops",
            "image": "shirt3.jpg",
            "bbox": [[35, 35], [165, 35], [165, 155], [35, 155]],
        },
    ]

    for ann in test_annotations:
        response = requests.post(
            f"{API_BASE}/api/v2/few-shot/item-type/annotate",
            json={
                "user_id": USER_ID,
                "image_path": f"/demo/{ann['image']}",
                "item_type": ann["item_type"],
                "bounding_box": ann["bbox"],
                "confidence": 1.0,
            },
        )
        if response.status_code == 200:
            print(f"   ✓ {ann['image']} ({ann['item_type']}) を追加")
        else:
            print(f"   ✗ {ann['image']} の追加に失敗")
    print()

    # 4. 学習を実行
    print("4. モデルの学習:")
    response = requests.post(
        f"{API_BASE}/api/v2/few-shot/item-type/train",
        json={"user_id": USER_ID, "min_samples_per_type": 3},
    )
    if response.status_code == 200:
        print("   ✓ 学習が完了しました")
        training_stats = response.json()["training_stats"]
        print(f"   - モデルタイプ: {training_stats.get('model_type', 'N/A')}")
        print(f"   - 学習完了時刻: {training_stats.get('training_completed', 'N/A')}")
    else:
        print("   ✗ 学習に失敗しました")
    print()

    # 5. 検出テスト
    print("5. 検出テスト:")
    test_images = ["test_dress.jpg", "test_tops.jpg", "test_unknown.jpg"]
    for img in test_images:
        response = requests.post(
            f"{API_BASE}/api/v2/few-shot/item-type/detect",
            json={"user_id": USER_ID, "image_path": f"/demo/{img}"},
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   - {img}:")
            if data["detections"]:
                for det in data["detections"]:
                    print(f"     - {det['item_type']}: 確信度 {det['confidence']:.2%}")
            else:
                print("     - アイテムが検出されませんでした")
        else:
            print(f"   - {img}: 検出に失敗")

    print("\n=== デモ完了 ===")
    print("UIでテストする場合: http://localhost:3032/#item-type-learning")


if __name__ == "__main__":
    main()
