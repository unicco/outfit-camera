import type { Dispatch, SetStateAction } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { TabsContent } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react';
import { formatNumber, formatCurrency } from '@/utils/numberUtils';
import {
  formatCategory,
  getPrimaryImageUrl,
  getTotalWearCount,
  getMostExpensiveCostPerWearLabel,
} from './analyticsTransforms';
import type { WardrobeRankings } from './types';

interface RankingsTabProps {
  rankings: WardrobeRankings | null;
  selectedCategory: string;
  setSelectedCategory: Dispatch<SetStateAction<string>>;
  selectedStatus: string;
  setSelectedStatus: Dispatch<SetStateAction<string>>;
}

export function RankingsTab({
  rankings,
  selectedCategory,
  setSelectedCategory,
  selectedStatus,
  setSelectedStatus,
}: RankingsTabProps) {
  return (
    <TabsContent value="rankings" className="space-y-4">
      {/* Filter Controls */}
      <div className="flex gap-4 flex-wrap">
        <Select value={selectedCategory} onValueChange={setSelectedCategory}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="全カテゴリ" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全カテゴリ</SelectItem>
            <SelectItem value="TOPS">トップス</SelectItem>
            <SelectItem value="BOTTOMS">ボトムス</SelectItem>
            <SelectItem value="OUTERWEAR">アウター</SelectItem>
            <SelectItem value="DRESSES">ワンピース</SelectItem>
            <SelectItem value="SHOES">シューズ</SelectItem>
            <SelectItem value="ACCESSORIES">アクセサリー</SelectItem>
            <SelectItem value="BAG">バッグ</SelectItem>
            <SelectItem value="OTHER">その他</SelectItem>
          </SelectContent>
        </Select>

        <Select value={selectedStatus} onValueChange={setSelectedStatus}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="ステータス" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ACTIVE">アクティブ</SelectItem>
            <SelectItem value="DISPOSED">保管中</SelectItem>
            <SelectItem value="all">全て</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {rankings && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Most Worn Ranking */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-green-600" />
                よく着るランキング
              </CardTitle>
              <CardDescription>着用回数が多い服 TOP 10</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {(rankings?.mostWorn || []).map((item, index) => {
                  const primaryImageUrl = getPrimaryImageUrl(item.imageUrls);
                  const totalWearCount = getTotalWearCount(item);
                  const brandLabel = item.brand || 'ノーブランド';
                  const subcategoryLabel = item.subcategory || formatCategory(item.category);
                  const purchasePriceLabel =
                    item.purchasePrice && item.purchasePrice > 0
                      ? formatCurrency(item.purchasePrice)
                      : null;

                  return (
                    <div key={item.id} className="flex items-center gap-3">
                      <div className="flex-shrink-0 w-8 h-8 bg-green-100 text-green-800 rounded-full flex items-center justify-center font-semibold text-sm">
                        {index + 1}
                      </div>
                      {primaryImageUrl && (
                        <img
                          src={primaryImageUrl}
                          alt={item.name}
                          className="w-12 h-12 object-cover rounded"
                        />
                      )}
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">
                            {brandLabel}
                          </span>
                          <Badge variant="secondary">{formatNumber(totalWearCount)} 回</Badge>
                        </div>
                        <div className="text-sm text-gray-500">
                          {subcategoryLabel}
                          {purchasePriceLabel ? ` • ${purchasePriceLabel}` : ''}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Least Worn Ranking */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingDown className="h-5 w-5 text-red-600" />
                着ていないランキング
              </CardTitle>
              <CardDescription>着用回数が少ない服 TOP 10</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {(rankings?.leastWorn || []).map((item, index) => {
                  const primaryImageUrl = getPrimaryImageUrl(item.imageUrls);
                  const totalWearCount = getTotalWearCount(item);
                  const brandLabel = item.brand || 'ノーブランド';
                  const subcategoryLabel = item.subcategory || formatCategory(item.category);
                  const purchasePriceLabel =
                    item.purchasePrice && item.purchasePrice > 0
                      ? formatCurrency(item.purchasePrice)
                      : null;

                  return (
                    <div key={item.id} className="flex items-center gap-3">
                      <div className="flex-shrink-0 w-8 h-8 bg-red-100 text-red-800 rounded-full flex items-center justify-center font-semibold text-sm">
                        {index + 1}
                      </div>
                      {primaryImageUrl && (
                        <img
                          src={primaryImageUrl}
                          alt={item.name}
                          className="w-12 h-12 object-cover rounded"
                        />
                      )}
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">
                            {brandLabel}
                          </span>
                          <Badge variant="destructive">{formatNumber(totalWearCount)} 回</Badge>
                        </div>
                        <div className="text-sm text-gray-500">
                          {subcategoryLabel}
                          {purchasePriceLabel ? ` • ${purchasePriceLabel}` : ''}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Most Expensive Ranking */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <DollarSign className="h-5 w-5 text-blue-600" />
                高額ランキング
              </CardTitle>
              <CardDescription>購入価格が高い服 TOP 10</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {(rankings?.mostExpensive || []).map((item, index) => {
                  const primaryImageUrl = getPrimaryImageUrl(item.imageUrls);
                  const totalWearCount = getTotalWearCount(item);
                  const brandLabel = item.brand || 'ノーブランド';
                  const subcategoryLabel = item.subcategory || formatCategory(item.category);
                  const purchasePriceLabel =
                    item.purchasePrice && item.purchasePrice > 0
                      ? formatCurrency(item.purchasePrice)
                      : null;
                  const costPerWearLabel = getMostExpensiveCostPerWearLabel(item, totalWearCount);

                  return (
                    <div key={item.id} className="flex items-center gap-3">
                      <div className="flex-shrink-0 w-8 h-8 bg-blue-100 text-blue-800 rounded-full flex items-center justify-center font-semibold text-sm">
                        {index + 1}
                      </div>
                      {primaryImageUrl && (
                        <img
                          src={primaryImageUrl}
                          alt={item.name}
                          className="w-12 h-12 object-cover rounded"
                        />
                      )}
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">
                            {brandLabel}
                          </span>
                          <span className="font-semibold">
                            {costPerWearLabel}
                          </span>
                        </div>
                        <div className="text-sm text-gray-500">
                          {purchasePriceLabel
                            ? `${subcategoryLabel} • 購入 ${purchasePriceLabel}`
                            : `${subcategoryLabel} • 購入情報なし`}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Best Cost Performance Ranking */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-purple-600" />
                コスパランキング
              </CardTitle>
              <CardDescription>1 回あたりのコストが低い服 TOP 10</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {(rankings?.bestCostPerformance || []).map((item, index) => {
                  const primaryImageUrl = getPrimaryImageUrl(item.imageUrls);
                  const brandLabel = item.brand || 'ノーブランド';
                  const subcategoryLabel = item.subcategory || formatCategory(item.category);
                  const purchasePriceLabel =
                    item.purchasePrice && item.purchasePrice > 0
                      ? formatCurrency(item.purchasePrice)
                      : null;

                  return (
                    <div key={item.id} className="flex items-center gap-3">
                      <div className="flex-shrink-0 w-8 h-8 bg-purple-100 text-purple-800 rounded-full flex items-center justify-center font-semibold text-sm">
                        {index + 1}
                      </div>
                      {primaryImageUrl && (
                        <img
                          src={primaryImageUrl}
                          alt={item.name}
                          className="w-12 h-12 object-cover rounded"
                        />
                      )}
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">
                            {brandLabel}
                          </span>
                          <span className="font-semibold text-green-600">
                            {formatCurrency(item.costPerWear || 0)} / 回
                          </span>
                        </div>
                        <div className="text-sm text-gray-500">
                          {subcategoryLabel}
                          {purchasePriceLabel ? ` • ${purchasePriceLabel}` : ''}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </TabsContent>
  );
}
