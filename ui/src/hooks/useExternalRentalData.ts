import { useCallback, useEffect, useState } from 'react';

import {
  fetchExternalRentalSummary,
  updateExternalRentalItem,
} from '@/services/externalRentals';
import type { ExternalRentalSummary } from '@/types/externalRentals';
import { logger } from '@/utils/logger';

interface UseExternalRentalDataOptions {
  autoLoad?: boolean;
  showMessage?: (text: string, type?: 'success' | 'error') => void;
}

interface UseExternalRentalDataResult {
  summary: ExternalRentalSummary | null;
  loading: boolean;
  error: string | null;
  actionItemId: string | null;
  reload: () => Promise<void>;
  incrementWear: (itemId: string) => Promise<void>;
  updateReturnDueDate: (itemId: string, isoDate: string) => Promise<void>;
  updateRentalCost: (itemId: string, rentalCost: number) => Promise<void>;
  markReturned: (itemId: string) => Promise<void>;
}

export const useExternalRentalData = ({
  autoLoad = true,
  showMessage,
}: UseExternalRentalDataOptions = {}): UseExternalRentalDataResult => {
  const [summary, setSummary] = useState<ExternalRentalSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(autoLoad);
  const [error, setError] = useState<string | null>(null);
  const [actionItemId, setActionItemId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setLoading(true);
      const result = await fetchExternalRentalSummary();
      setSummary(result);
      setError(null);
    } catch (err) {
      logger.error('Failed to fetch external rental summary', err);
      setError('レンタル情報の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (autoLoad) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 初期マウント時のデータ取得（reload 内部で setState）
      void reload();
    }
  }, [autoLoad, reload]);

  const incrementWear = useCallback(
    async (itemId: string) => {
      try {
        setActionItemId(itemId);
        await updateExternalRentalItem(itemId, { incrementWear: 1 });
        showMessage?.('レンタルの着用回数を更新しました');
        await reload();
      } catch (err) {
        logger.error('Failed to increment external rental wear', err);
        showMessage?.('レンタル着用回数の更新に失敗しました', 'error');
      } finally {
        setActionItemId(null);
      }
    },
    [reload, showMessage],
  );

  const updateReturnDueDate = useCallback(
    async (itemId: string, isoDate: string) => {
      try {
        setActionItemId(itemId);
        await updateExternalRentalItem(itemId, { returnDueDate: isoDate });
        showMessage?.('返却期限を更新しました');
        await reload();
      } catch (err) {
        logger.error('Failed to update external rental return due date', err);
        showMessage?.('返却期限の更新に失敗しました', 'error');
      } finally {
        setActionItemId(null);
      }
    },
    [reload, showMessage],
  );

  const updateRentalCost = useCallback(
    async (itemId: string, rentalCost: number) => {
      try {
        setActionItemId(itemId);
        await updateExternalRentalItem(itemId, { rentalCost });
        showMessage?.('レンタル料金を更新しました');
        await reload();
      } catch (err) {
        logger.error('Failed to update external rental cost', err);
        showMessage?.('レンタル料金の更新に失敗しました', 'error');
      } finally {
        setActionItemId(null);
      }
    },
    [reload, showMessage],
  );

  const markReturned = useCallback(
    async (itemId: string) => {
      try {
        setActionItemId(itemId);
        await updateExternalRentalItem(itemId, { status: 'RETURNED' });
        showMessage?.('レンタルを返却済にしました');
        await reload();
      } catch (err) {
        logger.error('Failed to mark external rental returned', err);
        showMessage?.('返却済の更新に失敗しました', 'error');
      } finally {
        setActionItemId(null);
      }
    },
    [reload, showMessage],
  );

  return {
    summary,
    loading,
    error,
    actionItemId,
    reload,
    incrementWear,
    updateReturnDueDate,
    updateRentalCost,
    markReturned,
  };
};
