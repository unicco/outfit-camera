import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

import { useOutfitData } from '../../hooks/use-outfit-data';
import { apiClient } from '@/services/apiClient';
import type { OutfitRecord, SimpleOutfitRecord } from '@/types/outfit';
import type { ExtendedClothingItem } from '@/types/wardrobe';

describe('useOutfitData', () => {
  const mockOutfitRecord: OutfitRecord = {
    id: 'record-1',
    photoId: 'photo-123',
    recordedAt: '2024-01-01T00:00:00Z',
    manualSelection: false,
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
    outfitItems: [],
  };

  const mockClothingItems = [
    {
      id: 'item-1',
      name: 'Shirt',
      category: 'tops',
    },
    {
      id: 'item-2',
      name: 'Jeans',
      category: 'bottoms',
    },
  ] as unknown as ExtendedClothingItem[];

  const mockBatchResults: Record<string, SimpleOutfitRecord> = {
    'photo-1': {
      photoId: 'photo-1',
      clothingItems: [],
    },
    'photo-2': {
      photoId: 'photo-2',
      clothingItems: [],
    },
  };

  const getSpy = vi.spyOn(apiClient, 'get');
  const postSpy = vi.spyOn(apiClient, 'post');

  const withStatus = (status: number, message?: string) =>
    Object.assign(new Error(message ?? ''), { status, message });

  beforeEach(() => {
    vi.clearAllMocks();
    getSpy.mockReset();
    postSpy.mockReset();
  });

  it('successfully fetches outfit data', async () => {
    getSpy.mockResolvedValueOnce(mockOutfitRecord);

    const { result } = renderHook(() => useOutfitData());

    let outfitResult: OutfitRecord | null = null;
    await act(async () => {
      outfitResult = await result.current.fetchOutfitForPhoto('photo-123');
    });

    expect(outfitResult).toEqual(mockOutfitRecord);
    expect(getSpy).toHaveBeenCalledWith('/api/v2/outfits/photo/photo-123');
  });

  it('returns null for 404 response', async () => {
    getSpy.mockRejectedValueOnce(withStatus(404));

    const { result } = renderHook(() => useOutfitData());

    let outfitResult: OutfitRecord | null = mockOutfitRecord;
    await act(async () => {
      outfitResult = await result.current.fetchOutfitForPhoto('photo-123');
    });

    expect(outfitResult).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('handles fetch errors', async () => {
    getSpy.mockRejectedValueOnce(withStatus(500, 'Server error occurred'));

    const { result } = renderHook(() => useOutfitData());

    let outfitResult: OutfitRecord | null = mockOutfitRecord;
    await act(async () => {
      outfitResult = await result.current.fetchOutfitForPhoto('photo-123');
    });

    expect(outfitResult).toBeNull();
    expect(result.current.error).toBe('Server error occurred');
  });

  describe('fetchOutfitItemsForPhoto', () => {
    it('returns clothing items on success', async () => {
      getSpy.mockResolvedValueOnce(mockClothingItems);

      const { result } = renderHook(() => useOutfitData());

      let items: ExtendedClothingItem[] = [];
      await act(async () => {
        items = await result.current.fetchOutfitItemsForPhoto('photo-123');
      });

      expect(items).toEqual(mockClothingItems);
      expect(getSpy).toHaveBeenCalledWith('/api/v2/outfits/photo/photo-123/clothing-items');
    });

    it('returns empty array for 404', async () => {
      getSpy.mockRejectedValueOnce(withStatus(404));

      const { result } = renderHook(() => useOutfitData());

      let items: ExtendedClothingItem[] = mockClothingItems;
      await act(async () => {
        items = await result.current.fetchOutfitItemsForPhoto('photo-123');
      });

      expect(items).toEqual([]);
      expect(result.current.error).toBeNull();
    });
  });

  describe('fetchOutfitsForPhotos', () => {
    it('fetches batch results', async () => {
      postSpy.mockResolvedValueOnce({ results: mockBatchResults });

      const { result } = renderHook(() => useOutfitData());

      let results: Record<string, SimpleOutfitRecord> = {};
      await act(async () => {
        results = await result.current.fetchOutfitsForPhotos(['photo-1', 'photo-2']);
      });

      expect(results).toEqual(mockBatchResults);
      expect(postSpy).toHaveBeenCalledWith('/api/v2/outfits/batch/simple', {
        photoIds: ['photo-1', 'photo-2'],
      });
    });

    it('returns empty object for empty input', async () => {
      const { result } = renderHook(() => useOutfitData());

      let results: Record<string, SimpleOutfitRecord> = mockBatchResults;
      await act(async () => {
        results = await result.current.fetchOutfitsForPhotos([]);
      });

      expect(results).toEqual({});
      expect(postSpy).not.toHaveBeenCalled();
    });

    it('enforces maximum photo limit', async () => {
      const { result } = renderHook(() => useOutfitData());
      const tooManyIds = Array.from({ length: 101 }, (_, i) => `photo-${i}`);

      let results: Record<string, SimpleOutfitRecord> = mockBatchResults;
      await act(async () => {
        results = await result.current.fetchOutfitsForPhotos(tooManyIds);
      });

      expect(results).toEqual({});
      expect(result.current.error).toContain('Too many photos');
      expect(postSpy).not.toHaveBeenCalled();
    });

    it('handles server errors gracefully', async () => {
      postSpy.mockRejectedValueOnce(withStatus(500, 'Server error occurred'));

      const { result } = renderHook(() => useOutfitData());

      let results: Record<string, SimpleOutfitRecord> = mockBatchResults;
      await act(async () => {
        results = await result.current.fetchOutfitsForPhotos(['photo-1']);
      });

      expect(results).toEqual({});
      expect(result.current.error).toBeNull();
    });
  });

  describe('loading state', () => {
    it('reflects loading transitions around fetches', async () => {
      getSpy.mockImplementation(
        () =>
          new Promise(resolve => {
            setTimeout(() => resolve(mockOutfitRecord), 50);
          })
      );

      const { result } = renderHook(() => useOutfitData());

      expect(result.current.loading).toBe(false);

      act(() => {
        void result.current.fetchOutfitForPhoto('photo-123');
      });

      expect(result.current.loading).toBe(true);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });
    });
  });
});
