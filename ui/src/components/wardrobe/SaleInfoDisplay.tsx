import React from 'react';
import { DollarSign, Info } from 'lucide-react';
import { getSalePlatformLabel } from '../../constants/wardrobe';
import type { ClothingItem } from '../../types/wardrobe';

interface SaleInfoDisplayProps {
  item: ClothingItem;
  onEdit?: () => void;
  editHint?: string;
}

export const SaleInfoDisplay: React.FC<SaleInfoDisplayProps> = ({
  item,
  onEdit,
  editHint,
}) => {
  const salePriceProvided =
    item.salePrice !== undefined && item.salePrice !== null;
  const saleCommissionProvided =
    item.saleCommission !== undefined && item.saleCommission !== null;
  const salePlatformProvided =
    typeof item.salePlatform === 'string' && item.salePlatform.trim().length > 0;

  const hasSaleTransactionData =
    salePriceProvided || saleCommissionProvided || salePlatformProvided;
  const hasDisposalDate = Boolean(item.disposalDate);

  const netAmount =
    hasSaleTransactionData || item.saleNetAmount !== undefined
      ? (item.saleNetAmount ??
          (item.salePrice || 0) - (item.saleCommission || 0))
      : null;

  const profitLoss =
    netAmount !== null && item.purchasePrice !== undefined && item.purchasePrice !== null
      ? item.saleProfitLoss ?? netAmount - item.purchasePrice
      : null;

  return (
    <>
      <div className="flex items-center justify-between">
        <h3 className="font-semibold flex items-center gap-2">
          <DollarSign className="h-4 w-4" />
          処分情報
        </h3>
        {onEdit && (
          <button
            className="text-sm text-blue-600 hover:text-blue-800"
            onClick={onEdit}
          >
            {hasSaleTransactionData || hasDisposalDate ? '編集' : '登録'}
          </button>
        )}
      </div>

      {!hasSaleTransactionData && !hasDisposalDate ? (
        <div className="text-center py-6 text-gray-500">
          <p className="text-sm">処分情報が未登録です</p>
        </div>
      ) : (
        <div className="space-y-2 text-sm">
          {salePlatformProvided && (
            <div className="flex justify-between">
              <span className="text-gray-600">売却先</span>
              <span className="font-medium">
                {getSalePlatformLabel(item.salePlatform!)}
              </span>
            </div>
          )}

          {salePriceProvided && item.salePrice !== undefined && (
            <div className="flex justify-between">
              <span className="text-gray-600">売却価格</span>
              <span className="font-medium">
                ¥{item.salePrice.toLocaleString()}
              </span>
            </div>
          )}

          {saleCommissionProvided && item.saleCommission !== undefined && (
            <div className="flex justify-between">
              <span className="text-gray-600">手数料</span>
              <span className="font-medium text-red-600">
                -¥{item.saleCommission.toLocaleString()}
              </span>
            </div>
          )}

          {netAmount !== null && (
            <div className="flex justify-between border-t border-gray-100 pt-2">
              <span className="font-medium text-gray-900">手取り金額</span>
              <span className="font-medium">
                ¥{netAmount.toLocaleString()}
              </span>
            </div>
          )}

          {profitLoss !== null && (
            <div className="flex justify-between">
              <span className="text-gray-600">損益</span>
              <span
                className={`font-medium ${
                  profitLoss >= 0 ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {profitLoss >= 0 ? '+' : ''}
                ¥{profitLoss.toLocaleString()}
              </span>
            </div>
          )}

          {netAmount !== null &&
            item.wearCount > 0 &&
            item.purchasePrice &&
            item.purchasePrice > 0 && (
              <div className="flex justify-between">
                <span className="text-gray-600">1 回あたりの金額</span>
                <span className="font-medium">
                  ¥{Math.round(
                    (item.purchasePrice - netAmount) / item.wearCount
                  ).toLocaleString()}
                </span>
              </div>
            )}

          {hasDisposalDate && (
            <div className="flex justify-between">
              <span className="text-gray-600">処分日</span>
              <span className="font-medium">
                {new Date(item.disposalDate!).toLocaleDateString('ja-JP')}
              </span>
            </div>
          )}

          {!hasSaleTransactionData && hasDisposalDate && (
            <div className="flex items-start gap-2 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-md p-2">
              <Info className="h-4 w-4 flex-shrink-0 mt-[1px]" />
              <span>処分日は登録済です。売却価格などの詳細は未入力です。</span>
            </div>
          )}
        </div>
      )}

      {editHint && !onEdit && (
        <div className="mt-2 flex items-start gap-2 text-xs text-gray-500">
          <Info className="h-4 w-4 flex-shrink-0 mt-[2px]" />
          <span>{editHint}</span>
        </div>
      )}
    </>
  );
};
