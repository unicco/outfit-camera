// apiClient のモック実装
import { vi } from 'vitest';

export const apiClient = {
  get: vi.fn().mockResolvedValue({}),
  post: vi.fn().mockResolvedValue({}),
  put: vi.fn().mockResolvedValue({}),
  delete: vi.fn().mockResolvedValue({}),
  patch: vi.fn().mockResolvedValue({}),
  head: vi.fn().mockResolvedValue(new Response(null, { status: 200 })),
  upload: vi.fn().mockResolvedValue({}),
  requestRaw: vi.fn().mockResolvedValue(new Response(null, { status: 200 })),
};

export const setReadOnlyMode = vi.fn();
export const isReadOnlyModeEnabled = vi.fn().mockReturnValue(false);
