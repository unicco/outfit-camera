import { getCategoryLabel, getSeasonLabel } from '@/constants/wardrobe';
import { formatCurrency } from '@/utils/numberUtils';
import type { WardrobeAnalyticsData, WardrobeRankingItem } from './types';

export const CHART_COLORS = [
  '#3B82F6', // blue
  '#10B981', // emerald
  '#F59E0B', // amber
  '#EF4444', // red
  '#8B5CF6', // violet
  '#EC4899', // pink
  '#14B8A6', // teal
  '#F97316', // orange
];

export const formatCategory = (category: string | null): string => {
  if (!category) return 'その他';
  return getCategoryLabel(category);
};

export const formatSeason = (season: string): string => {
  // 既存のgetSeasonLabel関数を使用
  return getSeasonLabel(season.toLowerCase());
};

export const getTotalWearCount = (item: WardrobeRankingItem) => {
  const baseWearCount = (item.usageCount ?? 0) + (item.defaultUsageCount ?? 0);
  return item.totalWearCount ?? baseWearCount;
};

export const getPrimaryImageUrl = (imageSources: WardrobeRankingItem['imageUrls']) => {
  if (!imageSources) {
    return null;
  }

  if (Array.isArray(imageSources)) {
    return (
      imageSources.find(
        (url): url is string => typeof url === 'string' && url.trim().length > 0
      ) ?? null
    );
  }

  if (typeof imageSources === 'object') {
    const preferredOrder = ['thumbnail', 'medium', 'small', 'large', 'original'];
    for (const key of preferredOrder) {
      const candidate = imageSources[key];
      if (typeof candidate === 'string' && candidate.trim().length > 0) {
        return candidate;
      }
    }
    const fallback = Object.values(imageSources).find(
      value => typeof value === 'string' && value.trim().length > 0
    );
    return (fallback as string | undefined) ?? null;
  }

  return null;
};

export const getMostExpensiveCostPerWearLabel = (
  item: WardrobeRankingItem,
  totalWearCount: number
): string => {
  const costPerWearValue =
    item.costPerWear ??
    (totalWearCount > 0 && item.purchasePrice
      ? item.purchasePrice / totalWearCount
      : undefined);
  const hasCostPerWear =
    costPerWearValue !== undefined && costPerWearValue !== null && costPerWearValue > 0;
  return hasCostPerWear ? `${formatCurrency(costPerWearValue)} / 回` : 'データなし';
};

export const getWearFrequencyChartData = (
  wearFrequency: WardrobeAnalyticsData['wearFrequency'] | undefined
) =>
  // 過去12ヶ月のデータを抽出し、月名を日本語形式に変換
  (wearFrequency || [])
    .slice(-12)
    .map(item => {
      const monthParts = item.month.split('-');
      const monthNumber = monthParts.length > 1 ? parseInt(monthParts[1], 10) : parseInt(item.month, 10);
      return {
        ...item,
        month: (!isNaN(monthNumber) ? monthNumber : item.month) + ' 月'
      };
    });

export const getCostByCategoryChartData = (
  byCategory: WardrobeAnalyticsData['costAnalysis']['byCategory'] | undefined
) =>
  (byCategory || []).map(item => ({
    ...item,
    categoryLabel: formatCategory(item.category)
  }));

export const getBrandSpendPercentage = (totalCost: number, totalValue: number): number =>
  (totalCost / totalValue || 1) * 100;
