import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';

export interface ClothingItemImageUrls {
  thumbnails?: {
    thumb_200?: string | null;
    thumb_400?: string | null;
  };
  original?: string | null;
}

export interface ClothingItemDetails {
  id?: string;
  name?: string;
  imageUrls?: ClothingItemImageUrls;
  image_urls?: ClothingItemImageUrls;
  costPerWear?: number | null;
}

type FetchItemDetailsResult =
  | { status: 'success'; details: ClothingItemDetails }
  | { status: 'not_found'; details: null }
  | { status: 'error'; details: null };

interface WardrobeCostSummary {
  total: number;
  calculableCount: number;
  loadingCount: number;
  missingCostCount: number;
}

interface UseItemDetailsResult {
  selectedItemsDetails: Record<string, ClothingItemDetails>;
  wardrobeCostError: string | null;
  wardrobeCostSummary: WardrobeCostSummary;
  displayedWardrobeTotal: number;
}

export const useItemDetails = (selectedItems: string[]): UseItemDetailsResult => {
  const [selectedItemsDetails, setSelectedItemsDetails] = useState<
    Record<string, ClothingItemDetails>
  >({});
  const [wardrobeCostError, setWardrobeCostError] = useState<string | null>(null);

  const wardrobeCostSummary = useMemo(() => {
    return selectedItems.reduce(
      (summary, itemId) => {
        const details = selectedItemsDetails[itemId];
        if (!details) {
          summary.loadingCount += 1;
          return summary;
        }

        const cost = details.costPerWear;
        if (typeof cost === 'number' && Number.isFinite(cost) && cost >= 0) {
          summary.total += cost;
          summary.calculableCount += 1;
        } else {
          summary.missingCostCount += 1;
        }
        return summary;
      },
      {
        total: 0,
        calculableCount: 0,
        loadingCount: 0,
        missingCostCount: 0,
      },
    );
  }, [selectedItems, selectedItemsDetails]);

  const displayedWardrobeTotal = useMemo(() => {
    // APIは着用コストを小数込みで返すため、画面表示は最も近い円単位に丸める
    return Math.round(wardrobeCostSummary.total);
  }, [wardrobeCostSummary.total]);

  // アイテム詳細を取得する関数
  const fetchItemDetails = useCallback(async (itemId: string): Promise<FetchItemDetailsResult> => {
    try {
      const itemData = await apiClient.get<ClothingItemDetails>(
        `/api/v2/wardrobe/items/${itemId}`
      );
      return { status: 'success', details: itemData };
    } catch (error: unknown) {
      const apiError = error as { status?: number };
      // 404エラーの場合は警告レベルでログ出力（削除されたアイテムの可能性）
      if (apiError?.status === 404) {
        logger.warn(`Item not found: ${itemId} (may have been deleted)`);
        return { status: 'not_found', details: null };
      } else {
        // その他のエラーはエラーレベルでログ出力
        logger.error('Failed to fetch item details:', error);
        return { status: 'error', details: null };
      }
    }
  }, []);

  // 選択されたアイテムの詳細を更新
  useEffect(() => {
    const missingItemIds = selectedItems.filter(itemId => !selectedItemsDetails[itemId]);
    if (missingItemIds.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 取得不要な状態へのエラークリア
      setWardrobeCostError(null);
      return;
    }

    let isCancelled = false;

    const fetchSelectedItemsDetails = async () => {
      const newDetails: Record<string, ClothingItemDetails> = {};
      let hasRequestError = false;

      for (const itemId of missingItemIds) {
        if (isCancelled) {
          break;
        }

        const result = await fetchItemDetails(itemId);
        if (isCancelled) {
          break;
        }

        // not_found は詳細なしのまま進める。エラー表示に混ぜない
        if (result.status === 'success' && result.details) {
          newDetails[itemId] = result.details;
        } else if (result.status === 'error') {
          hasRequestError = true;
        }
      }

      // 見つかったアイテムの詳細を更新
      if (!isCancelled && Object.keys(newDetails).length > 0) {
        setSelectedItemsDetails(prev => ({ ...prev, ...newDetails }));
      }

      if (!isCancelled) {
        setWardrobeCostError(
          hasRequestError
            ? 'コスト情報の取得に失敗しました。時間をおいて再度お試しください。'
            : null,
        );
      }
    };

    fetchSelectedItemsDetails();

    return () => {
      isCancelled = true;
    };
  }, [selectedItems, selectedItemsDetails, fetchItemDetails]);

  return {
    selectedItemsDetails,
    wardrobeCostError,
    wardrobeCostSummary,
    displayedWardrobeTotal,
  };
};
