// ApiClient モックパターンのテスト例
// 詳細なドキュメントは docs/api/apiClient.md を参照
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '@/services/apiClient';

// ApiClient は test/setup.ts で自動的にモック化される

describe('ApiClient モックパターンの例', () => {
  beforeEach(() => {
    // 各テストの前にモックをクリア
    vi.clearAllMocks();
  });

  describe('基本的な使い方', () => {
    it('GET リクエストのモック', async () => {
      // モックレスポンスを設定
      const mockData = { id: 1, name: 'Test Item' };
      vi.mocked(apiClient.get).mockResolvedValueOnce(mockData);

      // 実際の呼び出し（テスト対象のコード）
      const result = await apiClient.get('/items/1');

      // 結果の検証
      expect(result).toEqual(mockData);
      expect(apiClient.get).toHaveBeenCalledWith('/items/1');
      expect(apiClient.get).toHaveBeenCalledTimes(1);
    });

    it('POST リクエストのモック', async () => {
      const requestData = { name: 'New Item' };
      const responseData = { id: 2, ...requestData };

      vi.mocked(apiClient.post).mockResolvedValueOnce(responseData);

      const result = await apiClient.post('/items', requestData);

      expect(result).toEqual(responseData);
      expect(apiClient.post).toHaveBeenCalledWith('/items', requestData);
    });

    it('エラーレスポンスのモック', async () => {
      // エラーを作成
      interface ApiError extends Error {
        status?: number;
        statusText?: string;
      }
      const error = new Error('Not found') as ApiError;
      error.status = 404;
      error.statusText = 'Not Found';

      vi.mocked(apiClient.get).mockRejectedValueOnce(error);

      // エラーハンドリングのテスト
      await expect(apiClient.get('/items/999')).rejects.toThrow('Not found');
    });
  });

  describe('高度な使い方', () => {
    it('連続した呼び出しで異なるレスポンスを返す', async () => {
      vi.mocked(apiClient.get)
        .mockResolvedValueOnce({ id: 1 })
        .mockResolvedValueOnce({ id: 2 })
        .mockResolvedValueOnce({ id: 3 });

      const result1 = await apiClient.get('/items/1');
      const result2 = await apiClient.get('/items/2');
      const result3 = await apiClient.get('/items/3');

      expect(result1).toEqual({ id: 1 });
      expect(result2).toEqual({ id: 2 });
      expect(result3).toEqual({ id: 3 });
    });

    it('特定の引数に基づいてレスポンスを変える', async () => {
      interface User {
        id: number;
        name: string;
      }

      vi.mocked(apiClient.get).mockImplementation(async (path) => {
        if (path === '/users/1') {
          return { id: 1, name: 'Alice' };
        } else if (path === '/users/2') {
          return { id: 2, name: 'Bob' };
        }
        throw new Error('User not found');
      });

      const user1 = await apiClient.get<User>('/users/1');
      const user2 = await apiClient.get<User>('/users/2');

      expect(user1.name).toBe('Alice');
      expect(user2.name).toBe('Bob');

      await expect(apiClient.get('/users/999')).rejects.toThrow('User not found');
    });

    it('クエリパラメータを含む呼び出しの検証', async () => {
      const params = new URLSearchParams({ page: '1', limit: '10' });
      vi.mocked(apiClient.get).mockResolvedValueOnce({ items: [], total: 0 });

      await apiClient.get('/items', { params });

      expect(apiClient.get).toHaveBeenCalledWith('/items', { params });
    });

    it('ファイルアップロードのモック', async () => {
      const formData = new FormData();
      formData.append('file', new Blob(['test']), 'test.txt');

      const uploadResponse = { id: 'file-123', url: '/files/test.txt' };
      vi.mocked(apiClient.upload).mockResolvedValueOnce(uploadResponse);

      const result = await apiClient.upload('/upload', formData);

      expect(result).toEqual(uploadResponse);
      expect(apiClient.upload).toHaveBeenCalledWith('/upload', formData);
    });
  });

  describe('コンポーネントでの使用例', () => {
    it('非同期データ取得のモック', async () => {
      // コンポーネントが内部で apiClient を使用する場合の例
      const fetchUserData = async (userId: string) => {
        try {
          const user = await apiClient.get(`/users/${userId}`);
          const posts = await apiClient.get(`/users/${userId}/posts`);
          return { user, posts };
        } catch (error) {
          const apiError = error as { status?: number };
          if (apiError.status === 404) {
            return null;
          }
          throw error;
        }
      };

      // モックの設定
      vi.mocked(apiClient.get)
        .mockResolvedValueOnce({ id: '1', name: 'Test User' })
        .mockResolvedValueOnce([{ id: 'post-1', title: 'First Post' }]);

      const result = await fetchUserData('1');

      expect(result).toEqual({
        user: { id: '1', name: 'Test User' },
        posts: [{ id: 'post-1', title: 'First Post' }]
      });

      // 呼び出し順序の検証
      expect(apiClient.get).toHaveBeenNthCalledWith(1, '/users/1');
      expect(apiClient.get).toHaveBeenNthCalledWith(2, '/users/1/posts');
    });

    it('エラーハンドリングのテスト', async () => {
      const deleteItem = async (id: string) => {
        try {
          await apiClient.delete(`/items/${id}`);
          return { success: true };
        } catch (error) {
          const apiError = error as { status?: number };
          if (apiError.status === 403) {
            return { success: false, reason: 'permission_denied' };
          }
          return { success: false, reason: 'unknown_error' };
        }
      };

      // 権限エラーのモック
      interface ApiError extends Error {
        status?: number;
      }
      const error = new Error('Forbidden') as ApiError;
      error.status = 403;
      vi.mocked(apiClient.delete).mockRejectedValueOnce(error);

      const result = await deleteItem('protected-item');

      expect(result).toEqual({ success: false, reason: 'permission_denied' });
    });
  });

  describe('スパイとしての使用', () => {
    it('呼び出し回数と引数の詳細な検証', async () => {
      vi.mocked(apiClient.post).mockResolvedValue({ success: true });

      // 複数回の呼び出し
      await apiClient.post('/events', { type: 'click' });
      await apiClient.post('/events', { type: 'view' });
      await apiClient.post('/analytics', { metric: 'pageview' });

      // 呼び出し回数の検証
      expect(apiClient.post).toHaveBeenCalledTimes(3);

      // 特定のパスでの呼び出し回数
      const eventCalls = vi.mocked(apiClient.post).mock.calls
        .filter(([path]) => path === '/events');
      expect(eventCalls).toHaveLength(2);

      // 最後の呼び出しの検証
      expect(apiClient.post).toHaveBeenLastCalledWith(
        '/analytics',
        { metric: 'pageview' }
      );
    });
  });
});
