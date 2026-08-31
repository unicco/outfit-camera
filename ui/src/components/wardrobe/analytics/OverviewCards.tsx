import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { TrendingUp, Package, DollarSign, Activity } from 'lucide-react';
import { formatNumber, formatCurrency } from '@/utils/numberUtils';
import type { WardrobeAnalyticsData } from './types';

interface OverviewCardsProps {
  analytics: WardrobeAnalyticsData;
}

export function OverviewCards({ analytics }: OverviewCardsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">総服数</CardTitle>
          <Package className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {formatNumber(analytics?.overview?.totalItems || 0)}
            <span className="text-lg ml-1">着</span>
          </div>
          <div className="text-xs text-muted-foreground">
            アクティブ: {formatNumber(analytics?.overview?.activeItems || 0)} / 保管中:{' '}
            {formatNumber(analytics?.overview?.storedItems || 0)}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">総着用回数</CardTitle>
          <Activity className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {formatNumber(analytics?.overview?.totalWears || 0)}
            <span className="text-lg ml-1">回</span>
          </div>
          <div className="text-xs text-muted-foreground">
            平均: {analytics?.overview?.averageWearsPerItem?.toFixed(1) || '0.0'} 回
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">
            ワードローブ総額
          </CardTitle>
          <DollarSign className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {formatCurrency(analytics?.overview?.totalValue || 0)}
          </div>
          <div className="text-xs text-muted-foreground">購入価格の合計</div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">平均コストパフォーマンス</CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-green-600">
            {formatCurrency(analytics?.overview?.averageCostPerWear || 0)}
            <span className="text-lg ml-1">/ 回</span>
          </div>
          <div className="text-xs text-muted-foreground">
            1 回あたりの着用コスト
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
