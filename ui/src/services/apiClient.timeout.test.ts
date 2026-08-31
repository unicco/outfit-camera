// timeout の既定値が定数と一致しているかを実クラスで検証する。
// setup.ts が apiClient をグローバルにモックしているため unmock して実物を使う。
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.unmock('@/services/apiClient');

import { API_TIMEOUT } from '@/config/api';
import { ApiClient } from '@/services/apiClient';

describe('ApiClient の timeout 既定値', () => {
  let capturedSignal: AbortSignal | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    capturedSignal = undefined;
    // 応答しない fetch。abort されたかどうかだけを signal 経由で観測する
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        capturedSignal = init.signal ?? undefined;
        return new Promise<Response>(() => {});
      })
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('upload() は DEFAULT(5秒) 経過では abort しない', () => {
    const client = new ApiClient('');
    void client.upload('/api/v2/upload', new FormData());

    vi.advanceTimersByTime(API_TIMEOUT.DEFAULT + 1000);

    expect(capturedSignal?.aborted).toBe(false);
  });

  it('upload() は FILE_UPLOAD(30秒) で abort する', () => {
    const client = new ApiClient('');
    void client.upload('/api/v2/upload', new FormData());

    vi.advanceTimersByTime(API_TIMEOUT.FILE_UPLOAD);

    expect(capturedSignal?.aborted).toBe(true);
  });

  it('upload() は呼び出し元が明示した timeout を優先する', () => {
    const client = new ApiClient('');
    void client.upload('/api/v2/upload', new FormData(), { timeout: 1000 });

    vi.advanceTimersByTime(1000);

    expect(capturedSignal?.aborted).toBe(true);
  });

  it('post() は既定のままなので DEFAULT(5秒) で abort する', () => {
    const client = new ApiClient('');
    void client.post('/api/v2/items', { name: 'test' });

    vi.advanceTimersByTime(API_TIMEOUT.DEFAULT);

    expect(capturedSignal?.aborted).toBe(true);
  });
});
