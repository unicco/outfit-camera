import { useCallback, useMemo } from 'react';

import RentalSummarySection from '@/components/external-rentals/RentalSummarySection';
import { useExternalRentalData } from '@/hooks/useExternalRentalData';

interface RentalDashboardPageProps {
  showMessage: (text: string, type?: 'success' | 'error') => void;
}

const currencyFormatter = new Intl.NumberFormat('ja-JP', {
  style: 'currency',
  currency: 'JPY',
  maximumFractionDigits: 0,
});

const RentalDashboardPage = ({ showMessage }: RentalDashboardPageProps) => {
  const {
    summary,
    loading,
    error,
    actionItemId,
    reload,
    updateReturnDueDate,
    updateRentalCost,
    markReturned,
  } = useExternalRentalData({ autoLoad: true, showMessage });

  const handleUpdateDueDate = useCallback(
    async (itemId: string) => {
      const target = summary?.items.find(item => item.id === itemId);
      const defaultValue = target?.returnDueDate
        ? target.returnDueDate.slice(0, 10)
        : '';
      const input = window.prompt(
        '返却期限 (YYYY-MM-DD または 2025/02/20)',
        defaultValue,
      );
      if (input === null) {
        return;
      }
      const trimmed = input.trim();
      if (!trimmed) {
        showMessage('返却期限を入力してください', 'error');
        return;
      }

      await updateReturnDueDate(itemId, trimmed);
    },
    [summary, updateReturnDueDate, showMessage],
  );

  const handleUpdateRentalCost = useCallback(
    async (itemId: string) => {
      const target = [
        ...(summary?.items ?? []),
        ...(summary?.returnedItems ?? []),
      ].find(item => item.id === itemId);
      const defaultValue =
        target?.rentalCost != null ? String(Math.round(target.rentalCost)) : '';
      const input = window.prompt(
        'レンタル料金 (円) — このアイテムに割り付ける金額。キャンペーンや複数枚のときは按分額を入力',
        defaultValue,
      );
      if (input === null) {
        return;
      }
      const trimmed = input.trim();
      const parsed = Number(trimmed);
      if (!trimmed || !Number.isFinite(parsed) || parsed < 0) {
        showMessage('レンタル料金は 0 以上の数値で入力してください', 'error');
        return;
      }

      await updateRentalCost(itemId, parsed);
    },
    [summary, updateRentalCost, showMessage],
  );

  const handleMarkReturned = useCallback(
    async (itemId: string) => {
      if (!window.confirm('返却済として記録しますか？')) {
        return;
      }
      await markReturned(itemId);
    },
    [markReturned],
  );

  const planCostLabel = useMemo(() => {
    if (!summary) {
      return '—';
    }
    return currencyFormatter.format(summary.planCost);
  }, [summary]);

  const costPerWearLabel = useMemo(() => {
    if (!summary || summary.costPerWear == null) {
      return null;
    }
    return currencyFormatter.format(Math.round(summary.costPerWear));
  }, [summary]);

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <main className="mx-auto max-w-5xl px-4 py-6 space-y-6">
        <section className="rounded-xl border border-gray-200 bg-white px-4 py-4">
          <h2 className="text-base font-semibold text-gray-800">サマリー</h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-4 text-center">
              <p className="text-xs font-medium text-gray-500">月額プラン</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">{planCostLabel}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-4 text-center">
              <p className="text-xs font-medium text-gray-500">アクティブ件数</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">
                {summary?.activeItemCount ?? '—'} 件
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-4 text-center">
              <p className="text-xs font-medium text-gray-500">コスト / 着用</p>
              <p className="mt-1 text-xl font-semibold text-gray-900">
                {costPerWearLabel ?? '—'}
              </p>
            </div>
          </div>
        </section>

        <RentalSummarySection
          summary={summary}
          loading={loading}
          error={error}
          actionItemId={actionItemId}
          onRetry={() => {
            void reload();
          }}
          onUpdateDueDate={handleUpdateDueDate}
          onUpdateRentalCost={handleUpdateRentalCost}
          onMarkReturned={handleMarkReturned}
        />

        {summary && summary.items.length > 0 && (
          <p className="text-xs text-gray-400">
            画像は example_rental マイページから取得したサムネイルです。最新情報に更新するには Chrome 拡張で再取得してください。
          </p>
        )}
      </main>
    </div>
  );
};

export default RentalDashboardPage;
