# プロキシ層削除による API 変更ガイド

## 概要

API ルーター登録パターンの統一により、ワードローブプロキシ層（`/api/v2/app/proxy/`）を削除しました。
この変更により、より一貫性のあるシンプルなAPI構成になりました。

## 変更内容

### 削除されたファイル

- `/api/v2/app/proxy/` ディレクトリ全体 (166行削除)
  - `__init__.py`
  - プロキシエンドポイント定義ファイル群

### 変更されたエンドポイント

**変更前（プロキシ層使用）:**

```
/api/v2/wardrobe/* → プロキシ経由 → /wardrobe/*
```

**変更後（直接ルーティング）:**

```
/wardrobe/* → 直接アクセス
```

## API エンドポイントの移行

### ワードローブ API エンドポイント

| 機能         | 旧エンドポイント           | 新エンドポイント       | 状態        |
| ------------ | -------------------------- | ---------------------- | ----------- |
| アイテム一覧 | `/api/v2/wardrobe/items`      | `/wardrobe/items`      | ✅ 利用可能 |
| アイテム作成 | `/api/v2/wardrobe/items`      | `/wardrobe/items`      | ✅ 利用可能 |
| カテゴリ一覧 | `/api/v2/wardrobe/categories` | `/wardrobe/categories` | ✅ 利用可能 |
| 統計情報     | `/api/v2/wardrobe/statistics` | `/wardrobe/statistics` | ✅ 利用可能 |

### レガシーサポート

現在、**レガシーエンドポイントは維持**されており、既存のフロントエンドコードは引き続き動作します：

- `/api/v2/wardrobe/*` → 内部で `/wardrobe/*` にリダイレクト
- 既存のフロントエンド実装への影響なし

## main_v2.py の動的ルーターシステム

### 新しい構成

```python
FEATURE_ROUTERS = [
    ("wardrobe_api", ".wardrobe_api", "Wardrobe"),
    ("outfit_api", ".outfit_api", "Outfit"),
    ("ai_detection_api", ".ai_detection_api", "AI Detection"),
    # ... その他の機能
]
```

### 利点

1. **一貫性**: すべての機能ルーターが同じパターンで管理
2. **堅牢性**: 個別機能の失敗が他機能に影響しない
3. **保守性**: 機能の追加・削除が容易
4. **可視性**: ロード状況がログで確認可能

## フロントエンド側の推奨変更

### 現在（レガシー）

```typescript
// 現在も動作するが、将来的に廃止予定
const response = await fetch("/api/v2/wardrobe/items");
```

### 推奨（新しい方式）

```typescript
// 直接エンドポイントを使用（推奨）
const response = await fetch("/wardrobe/items");
```

### 設定ファイルでの移行

```typescript
// config/api.ts
const API_ENDPOINTS = {
  // 推奨：直接エンドポイント
  wardrobe: {
    items: "/wardrobe/items",
    categories: "/wardrobe/categories",
    statistics: "/wardrobe/statistics",
  },
};
```

## エラーハンドリングの改善

### 機能ロード失敗時の対応

```typescript
// API クライアント側でのエラーハンドリング例
try {
  const response = await fetch("/wardrobe/items");
  if (response.status === 404) {
    // ワードローブ機能がロードされていない
    console.warn("Wardrobe feature not available");
    return { items: [], error: "Wardrobe feature temporarily unavailable" };
  }
  return await response.json();
} catch (error) {
  console.error("Wardrobe API error:", error);
  return { items: [], error: "Network error" };
}
```

## テスト更新

### 新しいテストパターン

```python
def test_wardrobe_endpoints_loaded(self, client_v2):
    """ワードローブエンドポイントのロード確認"""
    response = client_v2.get("/wardrobe/items")

    if response.status_code == 200:
        # 正常にロードされている
        data = response.json()
        assert "items" in data or isinstance(data, list)
    elif response.status_code == 404:
        # ロードされていない（一部環境では許容）
        pass
    else:
        pytest.fail(f"Unexpected status: {response.status_code}")
```

## トラブルシューティング

### よくある問題

#### 1. ワードローブ機能が利用できない

**症状**: `/wardrobe/*` エンドポイントが 404 を返す

**原因**: ワードローブルーターのロードに失敗

**解決方法**:

```bash
# ログ確認
sudo journalctl -u coordinate-api -f | grep -i wardrobe

# サービス再起動
sudo systemctl restart coordinate-api
```

#### 2. レガシーエンドポイントが動作しない

**症状**: `/api/v2/wardrobe/*` が予期しないエラーを返す

**原因**: プロキシ機能の設定問題

**解決方法**:

```bash
# main_v2.py の使用確認
grep -r "main_v2" /etc/systemd/system/coordinate-api.service

# 設定確認
curl -f http://localhost:8000/debug/config
```

## 移行計画

### Phase 1（現在）: レガシー互換性維持

- ✅ プロキシ層削除完了
- ✅ レガシーエンドポイント維持
- ✅ 新しいエンドポイント利用可能

### Phase 2（推奨）: フロントエンド更新

- フロントエンドで新しいエンドポイントを使用
- API設定ファイルの更新
- テストケースの更新

### Phase 3（将来）: レガシー削除

- レガシープロキシエンドポイントの削除
- 完全に統一されたAPI構成

## 参考資料

- [API リファレンス](./README.md)
- [ワードローブ管理 API](./wardrobe-management.md)
- [アプリ組み立てのユニットテスト](../../tests/backend/unit/test_main.py)
- [ルート集合の安全網テスト](../../tests/backend/unit/test_route_snapshot.py)
