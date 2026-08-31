import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { MorningBriefDetailPage } from '../MorningBriefDetailPage';
import { apiClient } from '@/services/apiClient';

// apiClient.get をモックし、/today の表示を検証する。
// /today は本体（?schedule=skip）と人別コーデ（/schedule）を 2 本に分けて取得するため、
// URL でレスポンスを出し分ける。
vi.mock('@/services/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

const mockedGet = vi.mocked(apiClient.get);

type Photo = {
  photoId: string;
  photoUrl: string | null;
  capturedDate: string | null;
  items: unknown[];
  meetTitle?: string | null;
};
type Person = { name: string; photos: Photo[] };

// apiClient が snake→camel 変換した後の形（コンポーネントが受け取る形）。
function defaultBrief(): Record<string, unknown> {
  return {
    date: '2026-06-19',
    weather: {
      condition: 'sunny',
      temperature: 25,
      tempMax: 27,
      tempMin: 18,
      precipitationMm: 0,
      umbrellaRequired: false,
      available: true,
    },
    hero: null,
    items: [],
    schedule: { attendees: [], wornHistory: [] },
  };
}

function mockApi(options: {
  brief?: Record<string, unknown>;
  briefError?: boolean;
  wornHistory?: Person[];
}) {
  const brief = options.brief ?? defaultBrief();
  const wornHistory = options.wornHistory ?? [];
  const schedule = { attendees: wornHistory.map(p => p.name), wornHistory };
  mockedGet.mockImplementation((url: string) => {
    if (url.includes('/schedule')) {
      return Promise.resolve(schedule) as never;
    }
    if (options.briefError) {
      return Promise.reject(new Error('boom')) as never;
    }
    return Promise.resolve(brief) as never;
  });
}

describe('MorningBriefDetailPage', () => {
  beforeEach(() => {
    mockedGet.mockReset();
  });

  it('参加者ごとの見出し・相対日付・予定名を遅延ロードで並べる', async () => {
    // brief.date=2026-06-19 基準。06-09=10 日前 / 03-19=92 日=3 か月前
    mockApi({
      wornHistory: [
        {
          name: 'alice',
          photos: [
            {
              photoId: 'a',
              photoUrl: 'https://example/a.jpg',
              capturedDate: '2026-06-09',
              items: [],
              meetTitle: 'ランチ',
            },
            {
              photoId: 'b',
              photoUrl: 'https://example/b.jpg',
              capturedDate: '2026-03-19',
              items: [],
              meetTitle: null,
            },
          ],
        },
      ],
    });

    render(<MorningBriefDetailPage />);

    await waitFor(() =>
      expect(screen.getByText('alice と会った時')).toBeInTheDocument()
    );
    const imgs = screen.getAllByAltText('alice と会った時のコーデ');
    expect(imgs).toHaveLength(2);
    expect(screen.getByText('10 日前')).toBeInTheDocument();
    expect(screen.getByText('3 か月前')).toBeInTheDocument();
    // 予定名（meetTitle）が出る。null の写真には予定名行を出さない
    expect(screen.getByText('ランチ')).toBeInTheDocument();
  });

  it('1 年以上前は「N 年前」で出す', async () => {
    // brief.date=2026-06-19 基準。2025-05-01 は約 414 日 = 13 か月 → 1 年前
    mockApi({
      wornHistory: [
        {
          name: 'alice',
          photos: [
            {
              photoId: 'y',
              photoUrl: 'https://example/y.jpg',
              capturedDate: '2025-05-01',
              items: [],
            },
          ],
        },
      ],
    });

    render(<MorningBriefDetailPage />);

    await waitFor(() => expect(screen.getByText('1 年前')).toBeInTheDocument());
  });

  it('記録の無い参加者は空表示にする', async () => {
    mockApi({ wornHistory: [{ name: 'bob', photos: [] }] });

    render(<MorningBriefDetailPage />);

    await waitFor(() =>
      expect(screen.getByText('bob と会った時')).toBeInTheDocument()
    );
    expect(screen.getByText('まだ記録がありません')).toBeInTheDocument();
  });

  it('天気・傘・気温をまとめたバナーを出す', async () => {
    mockApi({}); // 既定 weather: umbrellaRequired=false / tempMax=27 / tempMin=18

    render(<MorningBriefDetailPage />);

    await waitFor(() => expect(screen.getByText('傘')).toBeInTheDocument());
    expect(screen.getByText('いらない')).toBeInTheDocument();
    expect(screen.getByText('最高 27° 最低 18°')).toBeInTheDocument();
  });

  it('ヒーロー写真のキャプションを年付きフル日付で出す', async () => {
    mockApi({
      brief: {
        ...defaultBrief(),
        hero: {
          photoId: 'h',
          photoUrl: 'https://example/h.jpg',
          capturedDate: '2025-09-21',
          temperatureMax: 26,
          temperatureMin: 19,
          matchedByTemperature: true,
        },
      },
    });

    render(<MorningBriefDetailPage />);

    await waitFor(() =>
      expect(screen.getByText(/気温が近い日の記録から/)).toBeInTheDocument()
    );
    expect(screen.getByText(/2025 年 9 月 21 日（日）/)).toBeInTheDocument();
  });

  it('ヒーロー写真が読めなければ壊れアイコンでなく欠損表示にする', async () => {
    // GCS から原本が失われた写真の記録が DB に残り得る
    mockApi({
      brief: {
        ...defaultBrief(),
        hero: {
          photoId: 'h',
          photoUrl: 'https://example/gone.jpg',
          capturedDate: '2025-09-13',
          temperatureMax: 28,
          temperatureMin: 22,
          matchedByTemperature: true,
        },
      },
    });

    render(<MorningBriefDetailPage />);

    fireEvent.error(await screen.findByAltText('コーディネート例'));

    await waitFor(() =>
      expect(screen.getByText('写真を表示できませんでした')).toBeInTheDocument()
    );
    expect(screen.queryByAltText('コーディネート例')).not.toBeInTheDocument();
  });

  it('構成アイテムの画像が読めなければ枠だけ残す', async () => {
    mockApi({
      brief: {
        ...defaultBrief(),
        items: [
          {
            id: 'i1',
            name: 'リネンシャツ',
            category: 'TOPS',
            imageUrl: 'https://example/gone.jpg',
          },
        ],
      },
    });

    render(<MorningBriefDetailPage />);

    fireEvent.error(await screen.findByAltText('リネンシャツ'));

    await waitFor(() =>
      expect(screen.queryByAltText('リネンシャツ')).not.toBeInTheDocument()
    );
    // 名前のラベルは残るので、どのアイテムが欠けたか分かる
    expect(screen.getByText('リネンシャツ')).toBeInTheDocument();
  });

  it('人別コーデの画像が読めなければ枠だけ残す', async () => {
    mockApi({
      wornHistory: [
        {
          name: 'alice',
          photos: [
            {
              photoId: 'p1',
              photoUrl: 'https://example/gone.jpg',
              capturedDate: '2026-06-09',
              items: [],
            },
          ],
        },
      ],
    });

    render(<MorningBriefDetailPage />);

    fireEvent.error(await screen.findByAltText('alice と会った時のコーデ'));

    await waitFor(() =>
      expect(
        screen.queryByAltText('alice と会った時のコーデ')
      ).not.toBeInTheDocument()
    );
    // 見出しと相対日付は残るので、どの日の記録が欠けたか分かる
    expect(screen.getByText('alice と会った時')).toBeInTheDocument();
    expect(screen.getByText('10 日前')).toBeInTheDocument();
  });

  it('本体の取得失敗時はエラー表示し、人別セクションは出さない', async () => {
    mockApi({ briefError: true });

    render(<MorningBriefDetailPage />);

    await waitFor(() =>
      expect(
        screen.getByText('コーデを取得できませんでした')
      ).toBeInTheDocument()
    );
    expect(screen.queryByText(/と会った時/)).not.toBeInTheDocument();
  });

  it('schedule だけ失敗しても本体は表示しページは成立する', async () => {
    // 本体は成功・schedule（/schedule）は失敗
    mockedGet.mockImplementation((url: string) => {
      if (url.includes('/schedule')) {
        return Promise.reject(new Error('ics down')) as never;
      }
      return Promise.resolve(defaultBrief()) as never;
    });

    render(<MorningBriefDetailPage />);

    await waitFor(() => expect(screen.getByText('傘')).toBeInTheDocument());
    expect(screen.queryByText(/と会った時/)).not.toBeInTheDocument();
    expect(
      screen.queryByText('今日会う人のコーデを読み込み中…')
    ).not.toBeInTheDocument();
  });
});
