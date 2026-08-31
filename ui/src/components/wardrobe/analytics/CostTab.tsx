import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { TabsContent } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Progress } from '@/components/ui/progress';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { formatNumber, formatCurrency } from '@/utils/numberUtils';
import { getCostByCategoryChartData, getBrandSpendPercentage } from './analyticsTransforms';
import type { WardrobeAnalyticsData } from './types';

interface CostTabProps {
  analytics: WardrobeAnalyticsData;
}

export function CostTab({ analytics }: CostTabProps) {
  return (
    <TabsContent value="cost" className="space-y-4">
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>コスト</CardTitle>
            <CardDescription>
              各カテゴリのコストパフォーマンス
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={getCostByCategoryChartData(analytics?.costAnalysis?.byCategory)}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="categoryLabel"
                    tick={{ dy: 10 }}
                  />
                  <YAxis />
                  <Tooltip
                    formatter={(value) => [`${formatCurrency(Number(value))}/回`]}
                    contentStyle={{ padding: '8px' }}
                  />
                  <Bar
                    dataKey="costPerWear"
                    fill="#10B981"
                    radius={[8, 8, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>ブランド別支出</CardTitle>
            <CardDescription>各ブランドへの総購入額</CardDescription>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[300px]">
              <div className="space-y-3">
                {(analytics?.costAnalysis?.byBrand || []).map(brand => (
                  <div key={brand.brand} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">
                        {brand.brand || 'ノーブランド'}
                      </span>
                      <span className="text-sm text-gray-500">
                        {formatNumber(brand.itemCount)} 着
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Progress
                        value={getBrandSpendPercentage(
                          brand.totalCost,
                          analytics?.overview?.totalValue
                        )}
                        className="flex-1"
                      />
                      <span className="text-sm font-medium w-24 text-right">
                        {formatCurrency(brand.totalCost)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </TabsContent>
  );
}
