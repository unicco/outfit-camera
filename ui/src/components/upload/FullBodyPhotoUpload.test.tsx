import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach, afterAll } from 'vitest';

import { FullBodyPhotoUpload } from './FullBodyPhotoUpload';
import { apiClient } from '@/services/apiClient';
import { unifiedAnalysisService } from '@/services/unifiedAnalysisService';
import type { UnifiedAnalysisResponse } from '@/services/unifiedAnalysisService';
import { dateUtils } from '@/utils/dateUtils';

// setup.ts の ApiClient モックはコンストラクタとして使えず、実体の生成が落ちる
vi.mock('@/services/unifiedAnalysisService', () => ({
  unifiedAnalysisService: { analyzePhoto: vi.fn() },
}));

type MutableURL = typeof URL & {
  createObjectURL?: (blob: Blob) => string;
  revokeObjectURL?: (url: string) => void;
};

const mutableURL = URL as MutableURL;
const originalCreateObjectURL = mutableURL.createObjectURL;
const originalRevokeObjectURL = mutableURL.revokeObjectURL;

mutableURL.createObjectURL = vi.fn(() => 'blob:mock');
mutableURL.revokeObjectURL = vi.fn();

afterAll(() => {
  if (originalCreateObjectURL) {
    mutableURL.createObjectURL = originalCreateObjectURL;
  } else {
    delete mutableURL.createObjectURL;
  }
  if (originalRevokeObjectURL) {
    mutableURL.revokeObjectURL = originalRevokeObjectURL;
  } else {
    delete mutableURL.revokeObjectURL;
  }
});

// upload / 分析の途中状態を掴むため、解決タイミングをテスト側で握る
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const analysisResponse: UnifiedAnalysisResponse = {
  photo_id: 'photo-1',
  segmentation: [],
  item_types: [],
  attributes: {},
  processing_time: { total: 1.2 },
  unified_results: [],
};

const mockedUpload = vi.mocked(apiClient.upload);
const mockedAnalyze = vi.mocked(unifiedAnalysisService.analyzePhoto);

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** ファイルを 1 枚選び、アップロードボタンを押した状態まで進める */
function startUpload() {
  const { container } = render(<FullBodyPhotoUpload apiUrl="http://test.local" />);

  const file = new File(['sample'], 'outfit.jpg', { type: 'image/jpeg' });
  const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(fileInput, { target: { files: [file] } });

  fireEvent.click(screen.getByRole('button', { name: 'アップロード' }));
}

describe('FullBodyPhotoUpload の進捗表示', () => {
  it('アップロード完了後にボタンが「分析中...」へ切り替わる', async () => {
    const upload = deferred<{ id: string }>();
    const analysis = deferred<UnifiedAnalysisResponse>();
    mockedUpload.mockReturnValue(upload.promise);
    mockedAnalyze.mockReturnValue(analysis.promise);

    startUpload();

    expect(await screen.findByRole('button', { name: 'アップロード中...' })).toBeInTheDocument();

    await act(async () => {
      upload.resolve({ id: 'photo-1' });
    });

    expect(screen.getByRole('button', { name: '分析中...' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'アップロード中...' })).not.toBeInTheDocument();

    await act(async () => {
      analysis.resolve(analysisResponse);
    });
  });

  it('アップロード中も分析中もアップロードボタンを押せない', async () => {
    const upload = deferred<{ id: string }>();
    const analysis = deferred<UnifiedAnalysisResponse>();
    mockedUpload.mockReturnValue(upload.promise);
    mockedAnalyze.mockReturnValue(analysis.promise);

    startUpload();

    expect(await screen.findByRole('button', { name: 'アップロード中...' })).toBeDisabled();

    await act(async () => {
      upload.resolve({ id: 'photo-1' });
    });

    expect(screen.getByRole('button', { name: '分析中...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'クリア' })).toBeDisabled();
    expect(mockedUpload).toHaveBeenCalledTimes(1);

    await act(async () => {
      analysis.resolve(analysisResponse);
    });
  });

  it('分析中は進捗カードを表示し、完了後に消える', async () => {
    const upload = deferred<{ id: string }>();
    const analysis = deferred<UnifiedAnalysisResponse>();
    mockedUpload.mockReturnValue(upload.promise);
    mockedAnalyze.mockReturnValue(analysis.promise);

    startUpload();

    await act(async () => {
      upload.resolve({ id: 'photo-1' });
    });

    expect(screen.getByText('MobileSAM で分析中...')).toBeInTheDocument();

    await act(async () => {
      analysis.resolve(analysisResponse);
    });

    await waitFor(() => {
      expect(screen.queryByText('MobileSAM で分析中...')).not.toBeInTheDocument();
    });
  });

  it('アップロードが失敗したらボタンが押せる状態に戻る', async () => {
    const upload = deferred<{ id: string }>();
    mockedUpload.mockReturnValue(upload.promise);

    startUpload();

    expect(await screen.findByRole('button', { name: 'アップロード中...' })).toBeInTheDocument();

    await act(async () => {
      upload.reject(new Error('boom'));
    });

    const uploadButton = screen.getByRole('button', { name: 'アップロード' });
    expect(uploadButton).toBeEnabled();
    expect(mockedAnalyze).not.toHaveBeenCalled();
  });

  it('分析が失敗しても進捗表示が残らない', async () => {
    const upload = deferred<{ id: string }>();
    const analysis = deferred<UnifiedAnalysisResponse>();
    mockedUpload.mockReturnValue(upload.promise);
    mockedAnalyze.mockReturnValue(analysis.promise);

    startUpload();

    await act(async () => {
      upload.resolve({ id: 'photo-1' });
    });

    expect(screen.getByText('MobileSAM で分析中...')).toBeInTheDocument();

    await act(async () => {
      analysis.reject(new Error('boom'));
    });

    await waitFor(() => {
      expect(screen.queryByText('MobileSAM で分析中...')).not.toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: '分析中...' })).not.toBeInTheDocument();
  });

  it('分析が失敗しても「アップロードしました」を success で出す', async () => {
    // 分析エンドポイントが未実装でこの経路が常に通るため、赤の失敗表示にしない。
    // 文言と severity を固定しないと、誤解を招く旧表示に黙って戻る
    const onSuccess = vi.fn();
    const upload = deferred<{ id: string }>();
    const analysis = deferred<UnifiedAnalysisResponse>();
    mockedUpload.mockReturnValue(upload.promise);
    mockedAnalyze.mockReturnValue(analysis.promise);

    // ⚠️ 撮影日を明示する。既定の `nowJST()` に任せると、テスト中に JST の日付境界を
    // 跨いだときだけ期待値とズレて落ちる（実装は正しいのに落ちる不安定なテストになる）
    const captured = new Date('2026-08-07T12:00:00+09:00');
    const { container } = render(
      <FullBodyPhotoUpload
        apiUrl="http://test.local"
        selectedDate={captured}
        onSuccess={onSuccess}
      />
    );
    const file = new File(['sample'], 'outfit.jpg', { type: 'image/jpeg' });
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'アップロード' }));

    await act(async () => {
      upload.resolve({ id: 'photo-1' });
    });
    await act(async () => {
      analysis.reject(new Error('boom'));
    });

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });

    // ⚠️ 部分一致では固定できない。「分析に失敗しましたが、…アップロードしました」でも
    // 通ってしまい、誤解を招く表示が戻ったことを検出できない（全文で照合する）
    const expectedDate = dateUtils.formatJSTJapanese(
      new Date(dateUtils.jstToDateString(captured))
    );
    expect(onSuccess.mock.calls[0][0]).toBe(`${expectedDate}の写真をアップロードしました`);

    // severity も固定する。文言だけ直しても赤で出ていれば利用者には失敗に見える
    expect(container.querySelector('.bg-green-50')).toBeInTheDocument();
    expect(container.querySelector('.bg-red-50')).toBeNull();
  });
});
