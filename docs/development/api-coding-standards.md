# API コーディング標準

このドキュメントは、Coordinate Recorder Manager の API 開発における標準とベストプラクティスを定めています。

## Pydantic モデルの使用規則

### ✅ 必須: カスタム BaseModel の使用

API レスポンスに使用する Pydantic モデルは、**必ず** `app.schemas.base.BaseModel` を継承してください。

**正しい例:**

```python
from app.schemas.base import BaseModel  # ✅ 正しい

class UserResponse(BaseModel):
    user_id: str
    user_name: str
    created_at: datetime
```

**間違った例:**

```python
from pydantic import BaseModel  # ❌ 禁止

class UserResponse(BaseModel):
    user_id: str
    user_name: str
    created_at: datetime
```

### 理由

カスタム BaseModel は自動的にフィールド名を変換します：

- Python 側: `user_name` (スネークケース)
- API レスポンス: `userName` (キャメルケース)

これにより、Python の慣習とJavaScript の慣習の両方を尊重しながら、API の一貫性を保ちます。

### チェック

`scripts/check-basemodel-usage.py` が間違った import を検出します：

```bash
❌ BaseModel usage errors found:

api/app/example.py:4: Direct import of pydantic.BaseModel is not allowed.
```

⚠️ **現在このチェックは自動実行されておらず、手で叩いても 0 件マッチで ✅ を返します。**検査対象のパスが実構成とずれているためです。緑を根拠にしないでください。

### 例外

以下のファイルは例外として `pydantic.BaseModel` の直接使用が許可されています：

- `settings.py` - 設定クラス
- `config.py` - 設定関連
- `schemas/base.py` - BaseModel 定義ファイル自体

## import の順序

標準的な import 順序：

```python
# 1. 標準ライブラリ
import os
from datetime import datetime
from typing import List, Optional

# 2. サードパーティライブラリ
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# 3. ローカルインポート
from ..database import get_db
from ..schemas.base import BaseModel  # Pydantic モデル用
from ..models import User
```

## API エンドポイントの設計

### レスポンスモデルの定義

```python
from ..schemas.base import BaseModel

class ItemResponse(BaseModel):
    """アイテムレスポンス"""
    item_id: str
    item_name: str
    created_at: datetime
    updated_at: datetime

@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: str) -> ItemResponse:
    # 実装
    pass
```

### リクエストモデルの定義

```python
class CreateItemRequest(BaseModel):
    """アイテム作成リクエスト"""
    item_name: str
    description: Optional[str] = None
    price: float

@router.post("/items", response_model=ItemResponse)
async def create_item(request: CreateItemRequest) -> ItemResponse:
    # 実装
    pass
```

## フィールド名の規則

### Python 側（内部実装）

- スネークケース: `user_name`, `created_at`, `is_active`

### API レスポンス（自動変換後）

- キャメルケース: `userName`, `createdAt`, `isActive`

### 特殊なケース

- `thumb_200` のような数字付きフィールドは変換されません
- 明示的に別名が必要な場合は `Field(alias="customName")` を使用

## テスト

新しい API エンドポイントを追加する際は：

1. レスポンスがキャメルケースになることを確認
2. 既存のフロントエンドとの互換性を確認
3. OpenAPI ドキュメント（/docs）でスキーマを確認

## トラブルシューティング

### "Direct import of pydantic.BaseModel is not allowed" エラー

```python
# 修正前
from pydantic import BaseModel

# 修正後
from app.schemas.base import BaseModel
# または
from ..schemas.base import BaseModel  # 相対インポート
```

### フィールドが変換されない

カスタム BaseModel を継承しているか確認：

```python
# schemas/base.py の内容を確認
from pydantic import BaseModel as PydanticBaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        validate_assignment=True,
    )
```

## 関連ドキュメント

- [API 命名規則の統一について](../api/naming-convention-migration.md)
- [FastAPI 公式ドキュメント](https://fastapi.tiangolo.com/)
- [Pydantic 公式ドキュメント](https://docs.pydantic.dev/)
