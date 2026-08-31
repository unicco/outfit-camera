import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';
import type {
  WardrobeAnalyticsData,
  WardrobeRankings,
  CategorySeasonMatrix,
} from './types';

export function useWardrobeAnalytics() {
  const [analytics, setAnalytics] = useState<WardrobeAnalyticsData | null>(null);
  const [rankings, setRankings] = useState<WardrobeRankings | null>(null);
  const [categorySeasonMatrix, setCategorySeasonMatrix] = useState<CategorySeasonMatrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState('all');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('ACTIVE');

  const fetchRankings = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        range: timeRange,
        limit: '10'
      });
      if (selectedCategory && selectedCategory !== 'all') {
        params.append('category', selectedCategory);
      }
      if (selectedStatus && selectedStatus !== 'all') {
        params.append('status', selectedStatus);
      }

      const data = await apiClient.get(`/api/v2/wardrobe/analytics/rankings?${params.toString()}`, {
        timeout: 15000, // 15秒のタイムアウト
      });
      setRankings(data.rankings);
    } catch (error) {
      logger.error('Failed to fetch rankings:', error);
      setError('ランキングデータの取得に失敗しました');
    }
  }, [timeRange, selectedCategory, selectedStatus]);

  const fetchCategorySeasonMatrix = useCallback(async () => {
    try {
      const data = await apiClient.get('/api/v2/wardrobe/analytics/category-season-matrix', {
        timeout: 15000, // 15秒のタイムアウト
      });
      setCategorySeasonMatrix(data);
    } catch (error) {
      logger.error('Failed to fetch category-season matrix:', error);
      setError('カテゴリ×季節データの取得に失敗しました');
    }
  }, []);

  const fetchAnalytics = useCallback(async () => {
    try {
      const data = await apiClient.get(`/api/v2/wardrobe/analytics/detailed?range=${timeRange}`, {
        timeout: 15000, // 15秒のタイムアウト
      });
      logger.dev('Analytics data received:', data);
      setAnalytics(data);
      setError(null);
    } catch (error) {
      logger.error('Failed to fetch analytics:', error);
      setError('分析データの取得に失敗しました');
    }
  }, [timeRange]);

  useEffect(() => {
    const fetchAllData = async () => {
      logger.dev('Starting to fetch all data...');
      setLoading(true);
      try {
        await Promise.all([
          fetchAnalytics(),
          fetchRankings(),
          fetchCategorySeasonMatrix()
        ]);
        logger.dev('All data fetched successfully');
      } catch (error) {
        logger.error('Error fetching data:', error);
      } finally {
        setLoading(false);
        logger.dev('Loading state set to false');
      }
    };
    fetchAllData();
  }, [fetchAnalytics, fetchRankings, fetchCategorySeasonMatrix]);

  return {
    analytics,
    rankings,
    categorySeasonMatrix,
    loading,
    error,
    timeRange,
    setTimeRange,
    selectedCategory,
    setSelectedCategory,
    selectedStatus,
    setSelectedStatus,
  };
}
