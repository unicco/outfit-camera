import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { OutfitCalendar } from '../OutfitCalendar';
import { apiClient } from '@/services/apiClient';

const mockedGet = vi.mocked(apiClient.get);

// URL に応じてレスポンスを出し分ける。
// - 月別の写真 / date-range: 空
// - wardrobe/items: フィルター用の服 1 件
// - wear-history: その服の着用日 2 件
function setupApi() {
  mockedGet.mockImplementation((path: string) => {
    if (path.includes('/api/v2/photos')) return Promise.resolve([]);
    if (path.includes('/api/v2/outfits/date-range')) return Promise.resolve([]);
    if (path.includes('/wear-history')) {
      return Promise.resolve({
        wearHistory: [{ date: '2026-07-01' }, { date: '2026-07-02' }],
        totalWears: 2,
        lastWorn: '2026-07-02',
      });
    }
    if (path.includes('/api/v2/wardrobe/items')) {
      return Promise.resolve([
        {
          id: 'item-1',
          name: '白シャツ',
          category: 'TOPS',
          brand: 'MUJI',
          status: 'ACTIVE',
          createdAt: '2026-01-01T00:00:00Z',
          wearCount: 2,
          imageUrls: { original: 'http://example.test/shirt.jpg' },
        },
      ]);
    }
    return Promise.resolve([]);
  });
}

describe('OutfitCalendar 服フィルター', () => {
  beforeEach(() => {
    mockedGet.mockReset();
    setupApi();
  });

  it('服を選ぶと着用日フィルターのバナーが表示され、解除できる', async () => {
    render(<OutfitCalendar apiUrl="http://example.test" />);

    // 初期ロード完了を待つ（絞り込みボタンが出る）
    const filterButton = await screen.findByRole('button', {
      name: '服で絞り込む',
    });
    fireEvent.click(filterButton);

    // ピッカーに服が並ぶ → 選択
    const itemButton = await screen.findByText('白シャツ');
    fireEvent.click(itemButton);

    // wear-history が引かれ、着用日数のバナーが出る
    await waitFor(() => {
      expect(screen.getByText('着用日 2 日')).toBeInTheDocument();
    });
    expect(mockedGet).toHaveBeenCalledWith(
      '/api/v2/wardrobe/items/item-1/wear-history'
    );

    // 解除するとバナーが消え、絞り込みボタンに戻る
    fireEvent.click(screen.getByLabelText('フィルターを解除'));
    await waitFor(() => {
      expect(screen.queryByText('着用日 2 日')).not.toBeInTheDocument();
    });
    expect(
      screen.getByRole('button', { name: '服で絞り込む' })
    ).toBeInTheDocument();
  });
});
