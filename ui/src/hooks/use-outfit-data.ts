/**
 * Hook for fetching outfit data for photos and dates
 */
import { useState, useCallback } from 'react';
import {
  OutfitRecord,
  BatchOutfitRequest,
  BatchOutfitResponse,
  SimpleOutfitRecord,
} from '@/types/outfit';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';

interface UseOutfitDataReturn {
  fetchOutfitForPhoto: (photoId: string) => Promise<OutfitRecord | null>;
  fetchOutfitItemsForPhoto: (
    photoId: string
  ) => Promise<ExtendedClothingItem[]>;
  fetchOutfitForDate: (date: string) => Promise<OutfitRecord | null>;
  fetchOutfitsForPhotos: (
    photoIds: string[]
  ) => Promise<Record<string, SimpleOutfitRecord>>;
  loading: boolean;
  error: string | null;
}

export const useOutfitData = (): UseOutfitDataReturn => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchOutfitForPhoto = useCallback(
    async (photoId: string): Promise<OutfitRecord | null> => {
      setLoading(true);
      setError(null);

      try {
        const outfitRecord = await apiClient.get<OutfitRecord>(`/api/v2/outfits/photo/${photoId}`);
        return outfitRecord;
      } catch (error) {
        const apiError = error as { status?: number; message?: string };
        logger.error('Failed to fetch outfit for photo:', photoId, error);
        if (apiError.status === 404) {
          // No outfit found for this photo
          return null;
        }
        setError(apiError.message || 'Failed to fetch outfit');
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const fetchOutfitItemsForPhoto = useCallback(
    async (photoId: string): Promise<ExtendedClothingItem[]> => {
      setLoading(true);
      setError(null);

      try {
        const clothingItems = await apiClient.get<ExtendedClothingItem[]>(
          `/api/v2/outfits/photo/${photoId}/clothing-items`
        );
        return clothingItems;
      } catch (error) {
        const apiError = error as { status?: number; message?: string };
        logger.error(
          'Failed to fetch clothing items for photo:',
          photoId,
          error
        );
        if (apiError.status === 404) {
          // No outfit found for this photo
          return [];
        }
        setError(apiError.message || 'Failed to fetch clothing items');
        return [];
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const fetchOutfitForDate = useCallback(
    async (date: string): Promise<OutfitRecord | null> => {
      setLoading(true);
      setError(null);

      try {
        // For manual outfits, we use a photo_id that includes the date (format: "manual-YYYY-MM-DD")
        const manualPhotoId = `manual-${date}`;
        const outfitRecord = await apiClient.get<OutfitRecord>(
          `/api/v2/outfits/photo/${manualPhotoId}`
        );
        return outfitRecord;
      } catch (error) {
        const apiError = error as { status?: number; message?: string };
        logger.error('Failed to fetch outfit for date:', date, error);
        if (apiError.status === 404) {
          // No outfit found for this date
          return null;
        }
        setError(apiError.message || 'Failed to fetch outfit');
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const fetchOutfitsForPhotos = useCallback(
    async (photoIds: string[]): Promise<Record<string, SimpleOutfitRecord>> => {
      if (photoIds.length === 0) {
        return {};
      }

      // クライアント側でもリクエストサイズを制限
      if (photoIds.length > 100) {
        logger.warn(
          'Too many photo IDs for batch request. Maximum 100 allowed.'
        );
        setError('Too many photos. Please reduce the number of photos.');
        return {};
      }

      setLoading(true);
      setError(null);

      try {
        const request: BatchOutfitRequest = { photoIds: photoIds };
        const batchResponse = await apiClient.post<BatchOutfitResponse>(
          '/api/v2/outfits/batch/simple',
          request
        );
        return batchResponse.results || {};
      } catch (error) {
        const apiError = error as { status?: number; message?: string };
        logger.error('Failed to fetch batch outfits:', error);
        if (apiError.status === 500) {
          logger.warn(
            'Server error when fetching batch outfits, returning empty result'
          );
          return {};
        }
        const errorMessage = apiError.message || 'Failed to fetch batch outfits';
        setError(errorMessage);
        // エラーが発生した場合は空のオブジェクトを返す
        return {};
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return {
    fetchOutfitForPhoto,
    fetchOutfitItemsForPhoto,
    fetchOutfitForDate,
    fetchOutfitsForPhotos,
    loading,
    error,
  };
};
