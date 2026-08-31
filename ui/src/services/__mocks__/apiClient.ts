// ApiClient のモック実装
import { vi } from 'vitest';

// モックの ApiClient クラス
export class ApiClient {
  constructor(public baseUrl = '') {}

  // 各メソッドをモック関数として定義
  get = vi.fn().mockResolvedValue({});
  post = vi.fn().mockResolvedValue({});
  put = vi.fn().mockResolvedValue({});
  delete = vi.fn().mockResolvedValue({});
  patch = vi.fn().mockResolvedValue({});
  head = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
  upload = vi.fn().mockResolvedValue({});
  requestRaw = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
}

// モックのインスタンス
export const apiClient = new ApiClient('/api');
export const setReadOnlyMode = vi.fn();
export const isReadOnlyModeEnabled = vi.fn().mockReturnValue(false);

// ヘルパー関数：成功レスポンスを設定
export const mockApiSuccess = <T>(method: keyof ApiClient, data: T) => {
  const mockMethod = apiClient[method] as ReturnType<typeof vi.fn>;
  mockMethod.mockResolvedValueOnce(data);
};

// ヘルパー関数：エラーレスポンスを設定
export const mockApiError = (method: keyof ApiClient, error: Error | { status?: number; message?: string }) => {
  const mockMethod = apiClient[method] as ReturnType<typeof vi.fn>;
  mockMethod.mockRejectedValueOnce(error);
};

// ヘルパー関数：すべてのモックをリセット
export const resetApiMocks = () => {
  Object.values(apiClient).forEach((method) => {
    if (typeof method === 'function' && 'mockReset' in method) {
      (method as ReturnType<typeof vi.fn>).mockReset();
    }
  });
};
