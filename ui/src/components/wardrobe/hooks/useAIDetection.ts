import { useCallback, useState } from 'react';

import { apiClient } from '@/services/apiClient';
import type { Photo } from '@/types/outfit';
import { logger } from '@/utils/logger';
import { isValidHttpUrl } from '@/utils/urlValidation';

import type { WardrobeMatchCandidate } from '../candidateScoring';

export interface DetectedItem {
  category?: string;
  croppedImageUrl?: string;  // camelCase に修正
  confidence?: number;
  bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  wardrobeMatchCandidates?: WardrobeMatchCandidate[];
}

export interface AIDetectionDetails {
  status: 'pending' | 'processing' | 'completed' | 'failed';
  annotatedImageUrl?: string;
  backgroundRemovedUrl?: string;
  croppedImages?: string[];
  errorMessage?: string;
  detectedItems?: DetectedItem[];
  detectionCount?: number;
  processingTimeMs?: number;
  modelVersion?: string;
  rawResults?: Record<string, unknown>;
}

interface PhotoMetadataResponse {
  aiDetectionStatus?: 'pending' | 'processing' | 'completed' | 'failed';
  aiDetectionError?: string;
  aiDetectionResults?: {
    detected_items?: DetectedItem[];
    detectedItems?: DetectedItem[];
    detectionCount?: number;
    detection_count?: number;
    processingTimeMs?: number;
    processing_time_ms?: number;
    modelVersion?: string;
    model_version?: string;
    background_removed_url?: string;
    backgroundRemovedUrl?: string;
  };
  aiCroppedImages?: string[];
  photoUrl?: string;  // GCS URL を追加
}

interface UseAIDetectionParams {
  photo: Photo;
  photoUrl: string | null;
  setPhotoUrl: React.Dispatch<React.SetStateAction<string | null>>;
  setIsLoadingPhoto: React.Dispatch<React.SetStateAction<boolean>>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
}

interface UseAIDetectionResult {
  aiDetectionDetails: AIDetectionDetails | null;
  isLoadingAIDetails: boolean;
  isReprocessingAIDetection: boolean;
  fetchAIDetectionDetails: () => Promise<void>;
  handleAIDetectionReprocess: () => Promise<void>;
}

export const useAIDetection = ({
  photo,
  photoUrl,
  setPhotoUrl,
  setIsLoadingPhoto,
  setError,
}: UseAIDetectionParams): UseAIDetectionResult => {
  const [aiDetectionDetails, setAiDetectionDetails] =
    useState<AIDetectionDetails | null>(null);
  const [isLoadingAIDetails, setIsLoadingAIDetails] = useState(false);
  const [isReprocessingAIDetection, setIsReprocessingAIDetection] = useState(false);

  // AI検出の詳細結果を取得
  const fetchAIDetectionDetails = useCallback(async () => {
    setIsLoadingAIDetails(true);
    try {
      const photoData = await apiClient.get<PhotoMetadataResponse>(`/api/v2/photos/${photo.id}/metadata`);

      const results = photoData.aiDetectionResults || {};
      const detectedItems = results.detected_items || results.detectedItems || [];
      const detectionCount =
        results.detectionCount || results.detection_count || detectedItems.length;

      if (photoData.aiDetectionStatus || detectedItems.length > 0) {
        // 切り抜き画像を収集
        const croppedImages = detectedItems
          .map((item: DetectedItem) => item.croppedImageUrl)
          .filter((url: string | undefined) => url) as string[];

        setAiDetectionDetails({
          status:
            photoData.aiDetectionStatus ||
            (detectedItems.length > 0 ? 'completed' : 'pending'),
          errorMessage: photoData.aiDetectionError,
          detectedItems: detectedItems,
          backgroundRemovedUrl: results.background_removed_url || results.backgroundRemovedUrl,
          croppedImages: croppedImages.length > 0 ? croppedImages : photoData.aiCroppedImages,
          detectionCount: detectionCount,
          processingTimeMs: results.processingTimeMs || results.processing_time_ms,
          modelVersion: results.modelVersion || results.model_version,
          rawResults: results,
        });
      } else {
        setAiDetectionDetails(null);
      }

      // photoUrl が既に設定されていない場合のみ、API レスポンスから取得
      if (!photoUrl && isValidHttpUrl(photoData.photoUrl)) {
        setPhotoUrl(photoData.photoUrl);
        setIsLoadingPhoto(false);
      } else if (!photoUrl) {
        setIsLoadingPhoto(false);
      }
    } catch (error) {
      logger.error('Failed to fetch AI detection details:', error);
      setIsLoadingPhoto(false);  // エラー時も読み込み状態を解除
      setError('写真の詳細情報を取得できませんでした。');
    } finally {
      setIsLoadingAIDetails(false);
    }
  }, [photo.id, photoUrl, setPhotoUrl, setIsLoadingPhoto, setError]);

  const handleAIDetectionReprocess = useCallback(async () => {
    if (!photo.id) {
      return;
    }
    setIsReprocessingAIDetection(true);
    setError(null);

    try {
      await apiClient.post(`/api/v2/photos/${photo.id}/ai-detection/reprocess`);
      setAiDetectionDetails(prev => ({
        status: 'pending',
        detectedItems: [],
        detectionCount: 0,
        processingTimeMs: prev?.processingTimeMs,
        modelVersion: prev?.modelVersion,
      }));
      await fetchAIDetectionDetails();
    } catch (error) {
      logger.error('Failed to reprocess AI detection:', error);
      setError('AI 検出の再解析に失敗しました。');
    } finally {
      setIsReprocessingAIDetection(false);
    }
  }, [photo.id, fetchAIDetectionDetails, setError]);

  return {
    aiDetectionDetails,
    isLoadingAIDetails,
    isReprocessingAIDetection,
    fetchAIDetectionDetails,
    handleAIDetectionReprocess,
  };
};
