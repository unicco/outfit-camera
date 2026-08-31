import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// 撮影時に置かれる未送信マークは、撮り直しても残っていた。捨てたはずの写真を再送ループが
// 拾い、その日の記録に並んでいた。破棄を通知する唯一の本番経路がここなので、
// 「撮り直しで discard を叩く」ことをコンポーネント側で固定する。
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

const PHOTO = 'photo_20260810_121711.jpg';

const discardCalls = () =>
  cameraPost.mock.calls.filter(([path]) => String(path).includes('/discard'));

/** 撮影ボタン → カウントダウン完了 → プレビュー表示まで進める. */
const captureUntilPreview = async () => {
  render(<TouchscreenApp apiUrl="http://api" cameraUrl="http://camera" />);

  fireEvent.click(screen.getByRole('button', { name: '撮影する' }));

  // カウントダウンは 7 秒。まとめて進めると 1 段しか動かない（次の setTimeout は
  // 再レンダのあとに張られるため）ので、1 秒ずつ act で刻む
  for (let i = 0; i < 8; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
  }

  // jsdom は img の load を発火しないので、プレビューの読み込み完了を自分で起こす
  // （撮り直しボタンは読み込み後にだけ出る）
  fireEvent.load(await screen.findByAltText('撮影した写真'));
};

describe('TouchscreenApp の撮り直し', () => {
  beforeEach(() => {
    // shouldAdvanceTime を付けないと、fake timers が testing-library の waitFor を
    // 止めてしまい（内部で実時間のタイマーを待つ）テストがタイムアウトする
    vi.useFakeTimers({ shouldAdvanceTime: true });
    cameraPost.mockReset();
    cameraGet.mockReset();
    cameraGet.mockResolvedValue({ enabled: false });
    cameraPost.mockResolvedValue({ status: 'success', filename: PHOTO, photo_id: PHOTO });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('捨てた写真の破棄をカメラサービスへ通知する', async () => {
    await captureUntilPreview();

    fireEvent.click(screen.getByRole('button', { name: '撮り直す' }));

    await waitFor(() => expect(discardCalls()).toHaveLength(1));
    // 撮影レスポンスのファイル名から組み立てる。URL ごと渡すと 404 になる
    expect(discardCalls()[0][0]).toBe(`/photo/${PHOTO}/discard`);
  });

  it('破棄の通知に失敗しても撮り直しは続けられる', async () => {
    await captureUntilPreview();

    cameraPost.mockRejectedValueOnce(new Error('camera service unreachable'));
    fireEvent.click(screen.getByRole('button', { name: '撮り直す' }));

    // 待たずに畳む＝通信の成否に関わらずスタンバイへ戻る（従来どおり撮り直せる）
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撮影する' })).toBeInTheDocument()
    );
  });
});
