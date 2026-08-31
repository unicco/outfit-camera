# API 開発への貢献ガイド

## 🚨 重要: BaseModel の使用ルール

新しい API エンドポイントを作成する際は、以下のルールに従ってください：

### ❌ 禁止事項

```python
from pydantic import BaseModel  # 直接インポートは禁止！

class MyResponse(BaseModel):
    user_id: str
```

### ✅ 正しい方法

```python
from app.schemas.base import BaseModel  # カスタム BaseModel を使用

class MyResponse(BaseModel):
    user_id: str  # API では "userId" として出力されます
```

### なぜこのルールがあるのか？

1. **一貫性**: すべての API レスポンスで統一された命名規則（キャメルケース）
2. **自動変換**: Python のスネークケースを JavaScript のキャメルケースに自動変換
3. **保守性**: 新しいフィールドも自動的に適切な形式に変換

### 自動チェック

⚠️ **自動チェックはありません。**以前は pre-commit フックから呼ばれる想定でしたが、そのフックは一度もインストールされておらず、設定ごと削除しました。さらに検査対象のパスが実構成とずれていて、手で叩いても 0 件マッチで ✅ を返します。

```bash
# エラーが出る場合の表示：
❌ BaseModel usage errors found:
api/app/my_api.py:4: Direct import of pydantic.BaseModel is not allowed.
```

### 手動チェック

```bash
# BaseModel の使用状況をチェック
python scripts/check-basemodel-usage.py
```

## クイックスタート例

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.base import BaseModel  # 👈 重要！

router = APIRouter(prefix="/api/v2/example", tags=["example"])


class ExampleRequest(BaseModel):
    """リクエストモデル"""
    item_name: str
    item_count: int


class ExampleResponse(BaseModel):
    """レスポンスモデル"""
    item_id: str
    item_name: str
    total_count: int
    created_at: datetime


@router.post("/items", response_model=ExampleResponse)
async def create_item(
    request: ExampleRequest,
    db: Session = Depends(get_db)
) -> ExampleResponse:
    # 実装
    return ExampleResponse(
        item_id="123",
        item_name=request.item_name,  # Python: item_name
        total_count=request.item_count,  # API: totalCount として出力
        created_at=datetime.now()  # API: createdAt として出力
    )
```

## 詳細情報

完全なガイドラインは [API コーディング標準](./api-coding-standards.md) を参照してください。
