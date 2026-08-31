import React, { useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { SALE_PLATFORMS } from '../../constants/wardrobe';
import type { ClothingItem } from '../../types/wardrobe';
import { logger } from '@/utils/logger';

interface SaleInfoFormProps {
  item: ClothingItem;
  onUpdate: (saleInfo: SaleInfoData) => Promise<void>;
  onCancel: () => void;
}

interface SaleInfoData {
  salePlatform?: string;
  salePrice?: number;
  saleCommission?: number;
  disposalDate?: string;
}

export const SaleInfoForm: React.FC<SaleInfoFormProps> = ({ item, onUpdate, onCancel }) => {
  const [formData, setFormData] = useState<SaleInfoData>({
    salePlatform: item.salePlatform || '',
    salePrice: item.salePrice || 0,
    saleCommission: item.saleCommission || 0,
    disposalDate: item.disposalDate || '',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Calculate net amount and profit/loss
  const netAmount = (formData.salePrice || 0) - (formData.saleCommission || 0);
  const profitLoss = item.purchasePrice
    ? netAmount - item.purchasePrice
    : null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    logger.dev('SaleInfoForm: Form submitted with data:', formData);

    try {
      await onUpdate(formData);
      logger.dev('SaleInfoForm: Update successful');
    } catch (error) {
      logger.error('SaleInfoForm: Failed to update sale info:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-3">
      <h3 className="font-semibold flex items-center gap-2">
        処分情報の更新
      </h3>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <Label htmlFor="salePlatform">売却先</Label>
          <Select
            value={formData.salePlatform}
            onValueChange={(value) => setFormData({ ...formData, salePlatform: value })}
          >
            <SelectTrigger>
              <SelectValue placeholder="売却先を選択" />
            </SelectTrigger>
            <SelectContent>
              {SALE_PLATFORMS.map((platform) => (
                <SelectItem key={platform.value} value={platform.value}>
                  {platform.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label htmlFor="salePrice">売却価格 (円)</Label>
          <Input
            id="salePrice"
            type="number"
            min="0"
            step="1"
            value={formData.salePrice || ''}
            onChange={(e) => setFormData({
              ...formData,
              salePrice: e.target.value ? parseFloat(e.target.value) : 0
            })}
            placeholder="売却価格を入力"
          />
        </div>

        <div>
          <Label htmlFor="saleCommission">手数料 (円)</Label>
          <Input
            id="saleCommission"
            type="number"
            min="0"
            step="1"
            value={formData.saleCommission || ''}
            onChange={(e) => setFormData({
              ...formData,
              saleCommission: e.target.value ? parseFloat(e.target.value) : 0
            })}
            placeholder="手数料を入力"
          />
        </div>

        <div>
          <Label htmlFor="disposalDate">処分日</Label>
          <Input
            id="disposalDate"
            type="date"
            value={formData.disposalDate}
            onChange={(e) =>
              setFormData({ ...formData, disposalDate: e.target.value })
            }
          />
        </div>

        {/* 計算結果の表示 */}
        <div className="bg-gray-50 p-4 rounded-lg space-y-2">
          <h4 className="font-medium">計算結果</h4>
          <div className="text-sm space-y-1">
            <div>手取り金額: ¥{netAmount.toLocaleString()}</div>
            {profitLoss !== null && (
              <div className={profitLoss >= 0 ? 'text-green-600' : 'text-red-600'}>
                損益: {profitLoss >= 0 ? '+' : ''}¥{profitLoss.toLocaleString()}
              </div>
            )}
            {item.wearCount > 0 && item.purchasePrice && (
              <div>
                1 回あたりの金額: ¥{Math.round((item.purchasePrice - netAmount) / item.wearCount).toLocaleString()}
              </div>
            )}
          </div>
        </div>

        <div className="flex gap-2 pt-4">
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? '更新中...' : '更新'}
          </Button>
          <Button type="button" variant="outline" onClick={onCancel}>
            キャンセル
          </Button>
        </div>
      </form>
    </div>
  );
};
