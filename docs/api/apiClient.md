# ApiClient 使用ガイド

## 概要

ApiClient は、プロジェクト全体で統一された API 呼び出しを提供するサービスです。
fetch() の直接使用を避け、以下の利点を提供します：

- 一貫したエラーハンドリング
- 自動タイムアウト処理
- リクエスト/レスポンスの変換
- TypeScript による型安全性

## 基本的な使い方

```typescript
import { apiClient } from "@/services/apiClient";

// GET リクエスト
const data = await apiClient.get<ResponseType>("/endpoint");

// POST リクエスト
const result = await apiClient.post<ResponseType>("/endpoint", {
  field: "value",
});

// PUT リクエスト
const updated = await apiClient.put<ResponseType>("/endpoint/id", {
  field: "newValue",
});

// DELETE リクエスト
await apiClient.delete("/endpoint/id");
```

## 高度な使い方

### クエリパラメータ

```typescript
// URLSearchParams を使用
const params = new URLSearchParams({ date: "2024-01-01", limit: "10" });
const data = await apiClient.get<ResponseType>("/records", { params });

// オブジェクトを使用
const data = await apiClient.get<ResponseType>("/records", {
  params: { date: "2024-01-01", limit: 10 },
});
```

### カスタムヘッダー

```typescript
const data = await apiClient.post("/endpoint", body, {
  headers: {
    "X-Custom-Header": "value",
  },
});
```

### タイムアウト制御

`timeout` オプション（ミリ秒）で指定する。値は `src/config/api.ts` の `API_TIMEOUT` から取り、数値を直書きしない。

```typescript
import { API_TIMEOUT } from "@/config/api";

const data = await apiClient.get("/endpoint", {
  timeout: API_TIMEOUT.LONG_RUNNING,
});
```

既定値は `API_TIMEOUT.DEFAULT`（5 秒）。`upload()` だけは `API_TIMEOUT.FILE_UPLOAD`（30 秒）が既定になる。

外から渡した `signal` は内部の AbortController に上書きされて効かない。中断は `timeout` で制御する。

### no-cors モード

```typescript
// CORS を回避する必要がある場合
const data = await apiClient.get("/external-endpoint", {
  mode: "no-cors",
});
```

## 特殊なメソッド

### HEAD リクエスト

```typescript
// Response オブジェクトを返す
const response = await apiClient.head("/health");
console.log(response.status); // 200
```

### ファイルアップロード

```typescript
const formData = new FormData();
formData.append("file", file);
formData.append("description", "My file");

const result = await apiClient.upload<UploadResponse>("/upload", formData);
```

タイムアウトは `API_TIMEOUT.FILE_UPLOAD`（30 秒）が既定。より長くかかる処理は呼び出し元で明示する。

### 生のレスポンスが必要な場合

```typescript
// requestRaw は Response オブジェクトをそのまま返す
const response = await apiClient.requestRaw("GET", "/stream");
const reader = response.body?.getReader();
```

## エラーハンドリング

ApiClient は自動的にエラーを分類し、適切なメッセージを提供します：

```typescript
try {
  const data = await apiClient.get("/endpoint");
} catch (error) {
  if (error instanceof Error) {
    // エラーには status と statusText が含まれる場合がある
    const apiError = error as ApiError;

    switch (apiError.status) {
      case 404:
        console.log("リソースが見つかりません");
        break;
      case 401:
        console.log("認証が必要です");
        break;
      case 500:
        console.log("サーバーエラーが発生しました");
        break;
      default:
        console.log(error.message);
    }
  }
}
```

## fetch() の直接使用が必要な場合

以下の場合のみ、fetch() の直接使用が許可されています。
必ず ESLint 無効化コメントを追加してください：

```typescript
// 1. 外部 URL のバリデーション
// eslint-disable-next-line no-restricted-globals
const response = await fetch(externalUrl, { method: "HEAD" });

// 2. 画像などのバイナリデータの取得
// eslint-disable-next-line no-restricted-globals
const imageResponse = await fetch(imageUrl);
const blob = await imageResponse.blob();

// 3. ストリーミングレスポンスの処理
// eslint-disable-next-line no-restricted-globals
const streamResponse = await fetch(streamUrl);
const reader = streamResponse.body?.getReader();
```

## テストでの使用

### 自動モック設定

ApiClient は `src/test/setup.ts` で自動的にモック化されているため、追加の設定なしで使用できます。

### 基本的なモックパターン

```typescript
import { vi } from "vitest";
import { apiClient } from "@/services/apiClient";

// モックレスポンスを設定
vi.mocked(apiClient.get).mockResolvedValueOnce({ data: "test" });

// テストを実行
const result = await myFunction();

// 呼び出しを検証
expect(apiClient.get).toHaveBeenCalledWith("/endpoint");
```

### 複雑なモックパターン

```typescript
// 連続した呼び出しで異なるレスポンス
vi.mocked(apiClient.get)
  .mockResolvedValueOnce({ id: 1 })
  .mockResolvedValueOnce({ id: 2 });

// エラーレスポンスのモック
const error = new Error("Not found") as any;
error.status = 404;
vi.mocked(apiClient.get).mockRejectedValueOnce(error);

// 条件に基づくレスポンス
vi.mocked(apiClient.get).mockImplementation(async (path) => {
  if (path.includes("/users/")) {
    return { id: "1", name: "Test User" };
  }
  throw new Error("Not found");
});
```

### コンポーネントテストの例

```typescript
describe('UserProfile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('ユーザー情報を表示する', async () => {
    const mockUser = { id: '1', name: 'Test User' };
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockUser);

    render(<UserProfile userId="1" />);

    await waitFor(() => {
      expect(screen.getByText('Test User')).toBeInTheDocument();
    });

    expect(apiClient.get).toHaveBeenCalledWith('/users/1');
  });
});
```

### モックヘルパー関数

`src/services/__mocks__/apiClient.ts` には便利なヘルパー関数が用意されています：

```typescript
import {
  mockApiSuccess,
  mockApiError,
  resetApiMocks,
} from "@/services/apiClient";

// 成功レスポンスの設定
mockApiSuccess("get", { data: "success" });

// エラーレスポンスの設定
mockApiError("post", new Error("Server error"));

// すべてのモックをリセット
resetApiMocks();
```

### 詳細なテスト例

完全なテスト例は以下のファイルを参照してください：

- `src/services/apiClient.test.ts` - ApiClient モックパターンの包括的な例
- `src/components/examples/ApiClientExample.test.tsx` - コンポーネントでの実践的な使用例

## 移行ガイド

### fetch() から ApiClient への移行

```typescript
// Before
const response = await fetch(`${API_URL}/photos`);
if (!response.ok) {
  throw new Error(`HTTP error! status: ${response.status}`);
}
const data = await response.json();

// After
const data = await apiClient.get<PhotoData[]>("/photos");
```

### エラーハンドリングの移行

```typescript
// Before
try {
  const response = await fetch(url);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return await response.json();
} catch (error) {
  console.error("Error:", error);
  return null;
}

// After
try {
  return await apiClient.get(path);
} catch (error) {
  if ((error as ApiError).status === 404) {
    return null;
  }
  console.error("Error:", error);
  return null;
}
```

## ベストプラクティス

1. **型を明示的に指定する**

   ```typescript
   const data = await apiClient.get<UserData>("/user");
   ```

2. **エラーハンドリングを適切に行う**

   ```typescript
   try {
     const data = await apiClient.get("/data");
   } catch (error) {
     // 404 は正常なケースとして扱う場合
     if ((error as ApiError).status === 404) {
       return defaultValue;
     }
     throw error;
   }
   ```

3. **不要な変換を避ける**

   ```typescript
   // skipTransform オプションで自動変換をスキップ
   const rawData = await apiClient.get("/raw-data", { skipTransform: true });
   ```

4. **適切なメソッドを使用する**
   - データ取得: `get()`
   - データ作成: `post()`
   - データ更新: `put()` または `patch()`
   - データ削除: `delete()`
   - ヘルスチェック: `head()`
   - ファイルアップロード: `upload()`
