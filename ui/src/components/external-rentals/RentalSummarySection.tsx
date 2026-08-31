import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { ExternalRentalItem, ExternalRentalSummary } from '@/types/externalRentals';

const currencyFormatter = new Intl.NumberFormat('ja-JP', {
  style: 'currency',
  currency: 'JPY',
  maximumFractionDigits: 0,
});

const formatReturnDateLabel = (value?: string | null): string | null => {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  }).format(parsed);
};

const formatCostPerWear = (value?: number | null): string | null => {
  if (value === null || value === undefined) {
    return null;
  }
  return currencyFormatter.format(Math.round(value));
};

const formatRentalCost = (value?: number | null): string | null => {
  if (value === null || value === undefined) {
    return null;
  }
  return currencyFormatter.format(Math.round(value));
};

const hasCost = (value?: number | null): value is number => value !== null && value !== undefined;

const hasWearCount = (item: ExternalRentalItem): boolean => (item.wearCount ?? 0) > 0;

interface RentalSummarySectionProps {
  summary: ExternalRentalSummary | null;
  loading: boolean;
  error: string | null;
  actionItemId: string | null;
  onRetry: () => void;
  onUpdateDueDate: (itemId: string) => void;
  onUpdateRentalCost: (itemId: string) => void;
  onMarkReturned: (itemId: string) => void;
}

export const RentalSummarySection = ({
  summary,
  loading,
  error,
  actionItemId,
  onRetry,
  onUpdateDueDate,
  onUpdateRentalCost,
  onMarkReturned,
}: RentalSummarySectionProps) => {
  if (loading) {
    return (
      <section className="rounded-xl border border-gray-200 bg-white px-4 py-3">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-32 rounded bg-gray-200" />
          <div className="h-4 w-full rounded bg-gray-200" />
          <div className="h-4 w-5/6 rounded bg-gray-200" />
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-xl border border-red-200 bg-red-50 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-red-700">{error}</p>
          <Button variant="outline" size="sm" onClick={onRetry}>
            再読み込み
          </Button>
        </div>
      </section>
    );
  }

  if (!summary) {
    return null;
  }

  const items = summary.items ?? [];
  const returnedItems = summary.returnedItems ?? [];
  const hasSummaryCost = hasCost(summary.costPerWear);
  const hasActiveItems = items.length > 0;
  const hasReturnedItems = returnedItems.length > 0;

  if (!hasActiveItems && !hasReturnedItems) {
    return null;
  }

  return (
    <section className="rounded-xl border border-gray-200 bg-white px-4 py-4">
      {hasActiveItems && (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-base font-semibold text-gray-800">レンタル中</h2>
            <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600">
              <span>
                月額 {currencyFormatter.format(summary.planCost)} / 着用 {summary.totalWearCount} 回
              </span>
              {hasSummaryCost && (
                <span>コスパ {formatCostPerWear(summary.costPerWear)}</span>
              )}
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {items.map(item => {
              const days = item.daysUntilDue ?? null;
              const isActioning = actionItemId === item.id;

              let badgeLabel = '期限未設定';
              let badgeVariant: 'outline' | 'secondary' | 'destructive' = 'outline';
              if (days !== null) {
                if (days < 0) {
                  badgeLabel = `期限切れ ${Math.abs(days)} 日`;
                  badgeVariant = 'destructive';
                } else if (days === 0) {
                  badgeLabel = '本日まで';
                  badgeVariant = 'destructive';
                } else if (days <= 3) {
                  badgeLabel = `残り ${days} 日`;
                  badgeVariant = 'secondary';
                } else {
                  badgeLabel = `残り ${days} 日`;
                }
              }

              const perWear = formatCostPerWear(item.costPerWear);
              const rentalCostLabel = formatRentalCost(item.rentalCost);

              return (
                <div
                  key={item.id}
                  className="rounded-lg border border-gray-200 bg-gray-50 p-4"
                >
                  <div className="flex w-full flex-col gap-4 md:flex-row md:items-start">
                    <div className="flex shrink-0 items-center justify-center">
                      {item.imageUrl ? (
                        <img
                          src={item.imageUrl}
                          alt={`${item.name} の画像`}
                          className="h-28 w-28 rounded-lg object-cover shadow-sm"
                        />
                      ) : (
                        <div className="flex h-28 w-28 items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white text-xs text-gray-400">
                          No Image
                        </div>
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">{item.name}</p>
                          <p className="text-sm text-gray-600">
                            {[item.brand, item.size].filter(Boolean).join(' / ') || 'ブランド不明'}
                          </p>
                          <p className="text-xs text-gray-500">
                            管理番号: {item.managementNumber ?? '—'}
                          </p>
                        </div>
                        <div className="flex flex-col items-end gap-2 text-right">
                          <Badge variant={badgeVariant}>{badgeLabel}</Badge>
                        </div>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                        <div className="text-sm text-gray-700">
                          着用 {item.wearCount} 回
                          {rentalCostLabel && (
                            <span className="ml-2 text-xs text-gray-500">
                              料金 {rentalCostLabel}
                            </span>
                          )}
                          {perWear && hasWearCount(item) && (
                            <span className="ml-2 text-xs text-gray-500">
                              コスパ {perWear}
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => onUpdateRentalCost(item.id)}
                            disabled={isActioning}
                          >
                            料金を編集
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => onUpdateDueDate(item.id)}
                            disabled={isActioning}
                          >
                            返却期限を編集
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => onMarkReturned(item.id)}
                            disabled={isActioning}
                          >
                            返却済
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      <div className={hasActiveItems ? 'mt-6 border-t border-gray-200 pt-4' : ''}>
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-gray-800">過去のレンタル</h3>
        </div>

        {hasReturnedItems ? (
          <div className="mt-4 space-y-3">
            {returnedItems.map(item => {
              const returnedDateLabel = formatReturnDateLabel(item.returnedAt);
              const perWear = formatCostPerWear(item.costPerWear);
              const rentalCostLabel = formatRentalCost(item.rentalCost);
              const isActioning = actionItemId === item.id;
              return (
                <div
                  key={item.id}
                  className="rounded-lg border border-gray-200 bg-gray-50 p-4"
                >
                  <div className="flex w-full flex-col gap-4 md:flex-row md:items-start">
                    <div className="flex shrink-0 items-center justify-center">
                      {item.imageUrl ? (
                        <img
                          src={item.imageUrl}
                          alt={`${item.name} の画像`}
                          className="h-24 w-24 rounded-lg object-cover shadow-sm"
                        />
                      ) : (
                        <div className="flex h-24 w-24 items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white text-xs text-gray-400">
                          No Image
                        </div>
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">{item.name}</p>
                          <p className="text-sm text-gray-600">
                            {[item.brand, item.size].filter(Boolean).join(' / ') || 'ブランド不明'}
                          </p>
                          <p className="text-xs text-gray-500">
                            管理番号: {item.managementNumber ?? '—'}
                          </p>
                        </div>
                        {returnedDateLabel && (
                          <span className="text-xs text-gray-500">
                            返却日 {returnedDateLabel}
                          </span>
                        )}
                      </div>
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                        <div className="text-sm text-gray-700">
                          着用 {item.wearCount} 回
                          {rentalCostLabel && (
                            <span className="ml-2 text-xs text-gray-500">
                              料金 {rentalCostLabel}
                            </span>
                          )}
                          {perWear && hasWearCount(item) && (
                            <span className="ml-2 text-xs text-gray-500">
                              コスパ {perWear}
                            </span>
                          )}
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => onUpdateRentalCost(item.id)}
                          disabled={isActioning}
                        >
                          料金を編集
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="mt-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-5 text-center text-sm text-gray-500">
            返却済のレンタルはありません
          </div>
        )}
      </div>
    </section>
  );
};

export default RentalSummarySection;
