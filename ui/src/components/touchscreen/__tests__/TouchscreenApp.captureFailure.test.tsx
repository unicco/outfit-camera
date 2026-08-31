import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// カメラサービスは撮影に失敗しても例外でなく 200 で {"status": "failed"} を返す。UI は
// これを成功として扱い、ファイル名の無いまま preview へ進んで存在しない写真を掴んでいた
// 失敗はスタンバイに戻すのが正しいので、その分岐を固定する。
const { cameraPost, cameraGet } = vi.hoisted(() => ({
  cameraPost: vi.fn(),
  cameraGet: vi.fn(),
}));

vi.mock('@/services/apiClient', () => {
  class MockApiClient {
    post = cameraPost;
    get = cameraGet;
  }
  return {
    ApiClient: MockApiClient,
    apiClient: new MockApiClient(),
    ApiError: class extends Error {},
  };
});

import { TouchscreenApp } from '../TouchscreenApp';

/** 撮影ボタン → カウントダウン完了まで進める（撮影レスポンスの処理まで走らせる）. */
const captureThroughCountdown = async () => {
  render(<TouchscreenApp apiUrl="http://api" cameraUrl="http://camera" />);

  fireEvent.click(screen.getByRole('button', { name: '撮影する' }));

  // カウントダウンは 7 秒。まとめて進めると 1 段しか動かないので 1 秒ずつ刻む
  for (let i = 0; i < 8; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
  }
};

/** 失敗後は 1 秒後にスタンバイへ戻す（setTimeout を進める）. */
const settleFailure = async () => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
};

describe('TouchscreenApp の撮影失敗', () => {
  let alertSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    cameraPost.mockReset();
    cameraGet.mockReset();
    cameraGet.mockResolvedValue({ enabled: false });
    alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
  });

  afterEach(() => {
    alertSpy.mockRestore();
    vi.useRealTimers();
  });

  it('status=failed の 200 応答をプレビューに進めない', async () => {
    cameraPost.mockResolvedValue({ status: 'failed', message: 'Photo capture failed' });

    await captureThroughCountdown();
    await settleFailure();

    expect(screen.queryByAltText('撮影した写真')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '撮影する' })).toBeInTheDocument();
  });

  it('カメラサービスが返した理由をそのまま知らせる', async () => {
    cameraPost.mockResolvedValue({ status: 'failed', message: 'Camera busy' });

    await captureThroughCountdown();

    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    expect(String(alertSpy.mock.calls[0][0])).toContain('Camera busy');
  });

  it('status=success でもファイル名が無ければ失敗として扱う', async () => {
    // unknown.jpg にフォールバックしていた経路。掴んでも 404 になるだけで理由が伝わらない
    cameraPost.mockResolvedValue({ status: 'success' });

    await captureThroughCountdown();
    await settleFailure();

    expect(screen.queryByAltText('撮影した写真')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '撮影する' })).toBeInTheDocument();
  });

  it('成功応答はこれまでどおりプレビューへ進む', async () => {
    cameraPost.mockResolvedValue({
      status: 'success',
      filename: 'photo_20260810_121711.jpg',
      photo_id: 'photo_20260810_121711.jpg',
    });

    await captureThroughCountdown();

    expect(await screen.findByAltText('撮影した写真')).toBeInTheDocument();
  });
});
