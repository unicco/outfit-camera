# API レスポンス命名規則の統一 (Issue #962)

## 概要

このドキュメントは、Issue #962 で実装した API レスポンスの命名規則統一について説明します。
Pydantic の `alias_generator` を使用して、Python のスネークケースを自動的に JavaScript のキャメルケースに変換する仕組みを導入しました。

## 背景

以前は API レスポンスでキャメルケースとスネークケースが混在しており、フロントエンドでの処理が複雑になっていました。

### 変更前の例

```json
{
  "date": "2025-09-11",
  "outfitRecordId": "6231cd3f-8a26-4892-b80c-6806c17ad2c7", // キャメルケース
  "photo_id": null, // スネークケース
  "clothingItems": [
    // キャメルケース
    {
      "id": "44b2aa6f-d255-4686-94c5-91ec2cf0764b",
      "name": "ノーブランド シューズ (white)",
      "category": "SHOES",
      "brand": "ノーブランド",
      "imageUrls": {
        // キャメルケース
        "original": "https://...",
        "thumbnails": {
          "thumb_200": "https://...", // スネークケース
          "thumb_400": "https://..." // スネークケース
        }
      }
    }
  ]
}
```

## 実装内容

### 1. 共通 BaseModel の作成

`api/app/schemas/base.py` に共通の BaseModel を作成し、`alias_generator` を設定しました。

```python
from pydantic import BaseModel as PydanticBaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class BaseModel(PydanticBaseModel):
    """Base model with automatic snake_case to camelCase conversion for JSON serialization"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        validate_assignment=True,
    )
```

### 2. 既存モデルの更新

#### outfit_api.py の変更

- 手動の `Field(alias=...)` 設定を削除
- `Config` クラスを削除
- 新しい `BaseModel` を継承

変更前:

```python
class ClothingDetectionResult(BaseModel):
    photo_id: str = Field(alias="photoId")
    detection_count: int = Field(alias="detectionCount")

    class Config:
        populate_by_name = True
```

変更後:

```python
class ClothingDetectionResult(BaseModel):
    photo_id: str
    detection_count: int
```

#### ai_detection_api_v2.py の変更

同様に、すべての Pydantic モデルから手動のエイリアス設定を削除し、共通 BaseModel を使用するように更新しました。

### 3. フロントエンド型定義の更新

`ui/src/types/outfit.ts` の型定義をキャメルケースに統一しました。

変更前:

```typescript
export interface SimpleClothingItem {
  id: string;
  name: string;
  category: string;
  brand?: string;
  image_urls?: unknown;
}
```

変更後:

```typescript
export interface SimpleClothingItem {
  id: string;
  name: string;
  category: string;
  brand?: string;
  imageUrls?: unknown;
}
```

## 変換ルール

- Python 側: スネークケース（`outfit_record_id`, `photo_id`, `clothing_items`）
- API レスポンス: キャメルケース（`outfitRecordId`, `photoId`, `clothingItems`）
- TypeScript 側: キャメルケース（JavaScript の慣習に従う）

## メリット

1. **一貫性**: すべての API レスポンスで統一された命名規則
2. **保守性**: 新しいフィールド追加時も自動的に適切な形式に変換
3. **開発効率**: 手動での変換やエイリアス設定が不要
4. **可読性**: 各言語の標準的な命名規則を維持

## 注意事項

- `thumb_200`, `thumb_400` のようなアンダースコア付き数字は変換されません（Pydantic の仕様）
- 新しい Pydantic モデルを作成する際は、必ず `schemas.base.BaseModel` を継承してください
- 既存の API クライアントコードは、新しいキャメルケース形式に対応する必要があります

## 影響を受けるエンドポイント

主要な影響を受けるエンドポイント:

- `/api/v2/outfits/date-range`
- `/api/v2/outfits/record`
- `/api/v2/outfits/photo/{photo_id}`
- `/api/v2/ai/detect`
- `/api/v2/ai-detection/standardize-clothing`
- `/api/v2/ai-detection/unify-background`

## 移行ガイド

### バックエンド開発者向け

1. 新しい Pydantic モデルを作成する場合:

   ```python
   from app.schemas.base import BaseModel

   class NewResponse(BaseModel):
       user_name: str  # API では userName として出力
       created_at: str  # API では createdAt として出力
   ```

2. 既存モデルを更新する場合:
   - `Field(alias=...)` を削除
   - `Config` クラスを削除
   - `from pydantic import BaseModel` を `from app.schemas.base import BaseModel` に変更

### フロントエンド開発者向け

1. API レスポンスの型定義をキャメルケースに更新
2. API クライアントコードで使用しているフィールド名をキャメルケースに変更
3. 必要に応じて、後方互換性のための変換ロジックを追加

## 今後の対応

- ✅ 他の API ファイル（wardrobe_api.py など）も同様の更新が必要 → **完了**
- API ドキュメント（OpenAPI/Swagger）の自動生成時にキャメルケース表記になることを確認
- 統合テストの追加

## 更新履歴

### Phase 1 (初回コミット)

- outfit_api.py と ai_detection_api_v2.py の更新
- 共通 BaseModel の作成
- フロントエンド型定義の更新

### Phase 2 (2回目のコミット)

- wardrobe_api.py, learning_api.py, bulk_upload_api.py の更新
- routers ディレクトリ内の全 API ファイルの更新
  - photos.py
  - outfit_analysis.py
  - google_photos.py
  - records.py
- api.py (メイン API ファイル) の更新

## 実装済ファイル一覧

以下のファイルで BaseModel 自動変換が有効化されています：

- `api/app/schemas/base.py` - 共通 BaseModel 定義
- `api/app/outfit_api.py`
- `api/app/ai_detection_api_v2.py`
- `api/app/wardrobe_api.py`
- `api/app/learning_api.py`
- `api/app/bulk_upload_api.py`
- `api/app/api.py`
- `api/app/routers/photos.py`
- `api/app/routers/outfit_analysis.py`
- `api/app/routers/google_photos.py`
- `api/app/routers/records.py`
