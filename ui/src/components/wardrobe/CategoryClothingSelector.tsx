import { useState, useEffect, useMemo, useCallback } from 'react';
import { Loader2, Crown, Shirt } from 'lucide-react';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import { transformApiResponse } from '@/utils/apiResponseTransformer';
import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';
import { dateUtils } from '@/utils/dateUtils';
import { getCategoryLabel } from '@/constants/wardrobe';

interface CategoryClothingSelectorProps {
  selectedItems: string[];
  onItemsChange: (items: string[]) => void;
  showSelectedCount?: boolean;
  photoId?: string;  // Add photoId to get AI recommendations
  selectedDate?: string | null;  // 過去日付選択時のフィルタリング制御用
}

interface CategoryData {
  name: string;
  items: ExtendedClothingItem[];
}

export function CategoryClothingSelector({
  selectedItems,
  onItemsChange,
  /* showSelectedCount = false, */ // 現在未使用
  photoId,
  selectedDate,
}: CategoryClothingSelectorProps) {
  const [clothingItems, setClothingItems] = useState<ExtendedClothingItem[]>(
    []
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isItemActiveForDate = useCallback(
    (item: ExtendedClothingItem, targetDate: string | null): boolean => {
      if (!targetDate) {
        return true;
      }

      const normalizedDate = targetDate.trim();
      if (!normalizedDate) {
        return true;
      }

      const targetTimestamp = dateUtils
        .parseDateAsJSTNoon(normalizedDate)
        .getTime();

      const parseDateToTimestamp = (value?: string | null): number | null => {
        if (!value) {
          return null;
        }
        try {
          return dateUtils.parseDateAsJSTNoon(value).getTime();
        } catch {
          return null;
        }
      };

      const purchaseTs = parseDateToTimestamp(item.purchaseDate);
      if (purchaseTs !== null && targetTimestamp < purchaseTs) {
        return false;
      }

      const disposalTs = parseDateToTimestamp(item.disposalDate);
      if (disposalTs !== null && targetTimestamp > disposalTs) {
        return false;
      }

      return true;
    },
    []
  );

  // Fetch clothing items
  useEffect(() => {
    const fetchClothingItems = async () => {
      try {
        setIsLoading(true);
        setError(null);

        const effectiveDate =
          selectedDate && selectedDate.trim().length > 0
            ? selectedDate
            : dateUtils.todayJST();

        const params = new URLSearchParams();
        if (photoId) {
          params.set('photo_id', photoId);
        }
        if (effectiveDate) {
          params.set('recorded_date', effectiveDate);
        }

        const queryString = params.toString();
        const endpoint = queryString
          ? `/api/v2/wardrobe/items?${queryString}`
          : '/api/v2/wardrobe/items';
        const rawItems = await apiClient.get(endpoint);
        const items: ExtendedClothingItem[] = transformApiResponse(rawItems);

        const filteredItems = items.filter(item =>
          isItemActiveForDate(item, effectiveDate)
        );

        setClothingItems(filteredItems);
      } catch (error) {
        logger.error('Error fetching clothing items:', error);
        setError(
          error instanceof Error
            ? error.message
            : '衣類アイテムの取得に失敗しました'
        );
      } finally {
        setIsLoading(false);
      }
    };

    fetchClothingItems();
  }, [photoId, selectedDate, isItemActiveForDate]);

  // AI推薦フィールドはAPIから直接取得されるため、マッピングは不要

  // Group items by category
  const categorizedItems: CategoryData[] = useMemo(() => {
    const seasonOrder = ['spring', 'summer', 'autumn', 'winter'];
    const targetDateString =
      selectedDate && selectedDate.trim().length > 0
        ? selectedDate
        : dateUtils.todayJST();
    const targetTimestamp = dateUtils.parseDateAsJSTNoon(
      targetDateString
    ).getTime();

    const parseDateToTimestamp = (value?: string | null): number | null => {
      if (!value) return null;
      try {
        return dateUtils.parseDateAsJSTNoon(value).getTime();
      } catch {
        return null;
      }
    };

    const getSeasonPriority = (item: ExtendedClothingItem): number => {
      const seasons = Array.isArray(item.season) ? item.season : [];
      const priorities = seasons
        .map(season => seasonOrder.indexOf(season.toLowerCase()))
        .filter(index => index >= 0);
      if (priorities.length === 0) {
        return seasonOrder.length;
      }
      return Math.min(...priorities);
    };

    const getUsageCount = (item: ExtendedClothingItem): number => {
      return (
        (item.wearCount || 0) +
        (item.defaultUsageCount || 0) +
        (item.actualUsageCount || 0)
      );
    };

    const getAiRanking = (item: ExtendedClothingItem): number => {
      return typeof item.aiRanking === 'number'
        ? item.aiRanking
        : Number.MAX_SAFE_INTEGER;
    };

    const isWithinLifecycle = (item: ExtendedClothingItem): boolean => {
      const purchaseTs = parseDateToTimestamp(item.purchaseDate);
      if (purchaseTs && targetTimestamp < purchaseTs) {
        return false;
      }
      const disposalTs = parseDateToTimestamp(item.disposalDate);
      if (disposalTs && targetTimestamp > disposalTs) {
        return false;
      }
      return true;
    };

    const getStatus = (item: ExtendedClothingItem): string =>
      (item.status || 'ACTIVE').toUpperCase();

    const categoryGroups: { [key: string]: ExtendedClothingItem[] } = {};

    clothingItems.forEach(item => {
      const category = item.category;
      if (!categoryGroups[category]) {
        categoryGroups[category] = [];
      }
      categoryGroups[category].push(item);
    });

    const categoryPriority = [
      'TOPS',
      'BOTTOMS',
      'DRESSES',
      'SHOES',
      'BAG',
      'OUTERWEAR',
      'SETS',
    ];

    return Object.entries(categoryGroups)
      .sort(([a], [b]) => {
        const aIndex = categoryPriority.indexOf(a);
        const bIndex = categoryPriority.indexOf(b);
        if (aIndex === -1 && bIndex === -1) return a.localeCompare(b);
        if (aIndex === -1) return 1;
        if (bIndex === -1) return -1;
        return aIndex - bIndex;
      })
      .map(([name, items]) => {
        // AI推薦（バッジ付き）アイテムはステータスに関わらずカテゴリー先頭に固定する。
        // ステータス別グループ分けの前に抜き出すことで、処分検討・その他ステータスでも
        // 必ず一番左に来るようにする（aiRanking 昇順）。
        const isAiRecommended = (item: ExtendedClothingItem): boolean =>
          item.isAiRecommended === true && typeof item.aiRanking === 'number';

        const aiRecommendedItems = [...items.filter(isAiRecommended)].sort(
          (a, b) => getAiRanking(a) - getAiRanking(b)
        );

        const nonAiItems = items.filter(item => !isAiRecommended(item));

        const activeItems = nonAiItems.filter(
          item => getStatus(item) === 'ACTIVE'
        );

        const disposalConsiderationItems = nonAiItems.filter(
          item => getStatus(item) === 'DISPOSAL_CONSIDERATION'
        );

        const otherLifecycleItems = nonAiItems.filter(item => {
          const status = getStatus(item);
          return (
            status !== 'ACTIVE' &&
            status !== 'DISPOSAL_CONSIDERATION' &&
            isWithinLifecycle(item)
          );
        });

        const sortedActiveItems = [...activeItems].sort((a, b) => {
          const aiDiff = getAiRanking(a) - getAiRanking(b);
          if (aiDiff !== 0) {
            return aiDiff;
          }

          const seasonDiff = getSeasonPriority(a) - getSeasonPriority(b);
          if (seasonDiff !== 0) {
            return seasonDiff;
          }

          const usageDiff = getUsageCount(b) - getUsageCount(a);
          if (usageDiff !== 0) {
            return usageDiff;
          }

          return (a.name || '').localeCompare(b.name || '');
        });

        const sortedDisposalItems = [...disposalConsiderationItems].sort(
          (a, b) => {
            const usageDiff = getUsageCount(b) - getUsageCount(a);
            if (usageDiff !== 0) {
              return usageDiff;
            }
            return (a.name || '').localeCompare(b.name || '');
          }
        );

        const sortedOtherItems = [...otherLifecycleItems].sort((a, b) => {
          const usageDiff = getUsageCount(b) - getUsageCount(a);
          if (usageDiff !== 0) {
            return usageDiff;
          }
          return (a.name || '').localeCompare(b.name || '');
        });

        const sortedItems = [
          ...aiRecommendedItems,
          ...sortedActiveItems,
          ...sortedDisposalItems,
          ...sortedOtherItems,
        ];

        return { name, items: sortedItems };
      });
  }, [clothingItems, selectedDate]);

  // Handle item toggle
  const onItemToggle = (itemId: string) => {
    const newSelectedItems = selectedItems.includes(itemId)
      ? selectedItems.filter(id => id !== itemId)
      : [...selectedItems, itemId];
    onItemsChange(newSelectedItems);
  };

  // Get image URL - prefer thumbnail from correct structure
  const getImageUrl = (item: ExtendedClothingItem): string => {
    // 現在の形式のみサポート
    if (
      item.imageUrls &&
      typeof item.imageUrls === 'object' &&
      !Array.isArray(item.imageUrls)
    ) {
      const imageUrls = item.imageUrls as Record<string, unknown>;
      // サムネイルを優先
      if (imageUrls.thumbnails?.thumb_200) {
        return imageUrls.thumbnails.thumb_200;
      }
      if (imageUrls.thumbnails?.thumb_400) {
        return imageUrls.thumbnails.thumb_400;
      }
      // オリジナル画像へフォールバック
      if (imageUrls.original) {
        return imageUrls.original;
      }
    }
    return '/placeholder-clothing.png';
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />
        <span>ワードローブを読み込み中...</span>
      </div>
    );
  }

  if (error) {
    return <div className="p-4 text-red-600 text-center">エラー: {error}</div>;
  }

  if (categorizedItems.length === 0) {
    return (
      <div className="p-8 text-center text-gray-500">
        ワードローブにアイテムがありません
      </div>
    );
  }

  return (
    <div className="space-y-6 pt-4">
      {categorizedItems.map(category => (
        <div key={category.name} className="space-y-3">
          <h3 className="font-medium text-gray-900 px-4">
            {getCategoryLabel(category.name)} ({category.items.length})
          </h3>

          <div className="overflow-x-auto">
            <div className="flex gap-3 px-4 pb-2">
              {category.items.map(item => {
                const isSelected = selectedItems.includes(item.id);

                // AI推薦情報を直接アイテムから取得
                const isAiRecommended = item.isAiRecommended || false;
                const aiRanking = item.aiRanking || -1;
                const aiMatchScore = item.aiMatchScore || 0;

                // ツールチップ用のタイトル
                const tooltipText = isAiRecommended
                  ? `${item.name}\n${aiRanking}位 - ${(aiMatchScore * 100).toFixed(1)}% マッチ`
                  : item.name;

                return (
                  <div key={item.id} className="relative flex-shrink-0 group">
                    <button
                      onClick={() => onItemToggle(item.id)}
                      title={tooltipText}
                      className={`
                        w-20 h-20 rounded-lg overflow-hidden border-2 transition-all relative
                        ${
                          isSelected
                            ? 'border-blue-500 ring-2 ring-blue-200'
                            : 'border-gray-200 hover:border-gray-300'
                        }
                      `}
                    >
                      {getImageUrl(item) === '/placeholder-clothing.png' ? (
                        <div className="w-full h-full bg-gray-100 flex items-center justify-center">
                          <Shirt className="w-8 h-8 text-gray-400" />
                        </div>
                      ) : (
                        <img
                          src={getImageUrl(item)}
                          alt={item.name}
                          className="w-full h-full object-cover"
                          onError={e => {
                            const target = e.currentTarget as HTMLImageElement;
                            target.style.display = 'none';
                            target.parentElement?.insertAdjacentHTML(
                              'afterbegin',
                              '<div class="w-full h-full bg-gray-100 flex items-center justify-center"><svg class="w-8 h-8 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.38 8.57l-1.23 1.85a8 8 0 0 1-7.22 4.44 8 8 0 0 1-7.22-4.44L3.48 8.57a2 2 0 0 1 .43-2.75l2.83-2.12a2 2 0 0 1 2.44.11l2.32 2.32 2.32-2.32a2 2 0 0 1 2.44-.11l2.83 2.12a2 2 0 0 1 .43 2.75zM7 17h10"></path></svg></div>'
                            );
                          }}
                        />
                      )}
                    </button>

                    {/* カスタムツールチップ（AI推薦アイテムのみ） */}
                    {isAiRecommended && (
                      <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none z-10">
                        <div className="bg-gray-900 text-white text-xs rounded-lg py-2 px-3 whitespace-nowrap">
                          <div className="font-semibold">{item.name}</div>
                          <div className="text-yellow-300">
                            {aiRanking}位 -{' '}
                            {(aiMatchScore * 100).toFixed(1)}% マッチ
                          </div>
                          <div className="text-gray-300">
                            AI推薦アイテム
                          </div>
                          {/* 矢印 */}
                          <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900"></div>
                        </div>
                      </div>
                    )}

                    {/* AI推薦ランキングバッジ */}
                    {isAiRecommended && aiRanking > 0 && (
                      <div className="absolute top-0 right-0 flex items-center justify-center w-6 h-6 bg-yellow-500 text-white text-xs font-bold rounded-full border-2 border-white shadow-sm">
                        {aiRanking === 1 && <Crown className="w-3 h-3" />}
                        {aiRanking > 1 && aiRanking}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
