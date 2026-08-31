# 精度評価フレームワーク

ワードローブマッチングの精度を定量的に評価するためのツール。

## ディレクトリ構成

```
scripts/evaluation/
├── evaluate_wardrobe_matching.py   # ワードローブマッチング精度の評価（Hit@K）
├── test_images/                    # テスト画像を配置するディレクトリ
├── matching_ground_truth.json      # マッチングの正解データ
└── README.md                       # このファイル
```

## テスト画像の準備

1. システムが出力する切り抜き済衣類画像（RGBA PNG、alpha マスク付き）を使用する
2. `test_images/` ディレクトリに配置する
3. ファイル名は正解データの JSON キーと一致させる

### 画像の取得方法

- **本番データから取得**: API の検出結果として保存される切り抜き画像を使用
- **手動で作成**: 写真から衣類部分を切り抜き、背景を透過にした PNG を作成

## ワードローブマッチング精度の評価（Hit@K）

### 前提条件

- DB 接続が必要（`DATABASE_URL` 環境変数）
- `JINA_API_KEY` 環境変数が必要
- ワードローブに embedding 計算済のアイテムが登録されていること

### 正解データの記述

`matching_ground_truth.json` に以下の形式でエントリを追加する:

```json
{
    "navy_jacket_001.png": {
        "correct_item_id": 42,
        "category": "outerwear",
        "notes": "ネイビージャケット"
    }
}
```

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `correct_item_id` | Yes | 正解のワードローブアイテム ID |
| `category` | No | カテゴリでフィルタする場合に指定 |
| `notes` | No | 補足情報 |

### 実行

```bash
# 基本的な実行（Hit@1, Hit@3, Hit@5）
python scripts/evaluation/evaluate_wardrobe_matching.py

# K 値を指定
python scripts/evaluation/evaluate_wardrobe_matching.py --k 1 3 5 10

# 結果を JSON ファイルに保存
python scripts/evaluation/evaluate_wardrobe_matching.py --output matching_results.json
```

### 結果の見方

- **Hit@K**: Top-K 件の中に正解アイテムが含まれる割合
  - `Hit@1`: 1位に正解がある割合（最も厳密）
  - `Hit@3`: 3位以内に正解がある割合
  - `Hit@5`: 5位以内に正解がある割合
- **正解アイテム順位**: 正解アイテムが何位にランクされたかの統計
