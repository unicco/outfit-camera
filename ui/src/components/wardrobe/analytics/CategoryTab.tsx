import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { TabsContent } from '@/components/ui/tabs';
import { getCategoryLabel } from '@/constants/wardrobe';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { formatNumber, formatCurrency } from '@/utils/numberUtils';
import { CHART_COLORS, formatCategory } from './analyticsTransforms';
import type { WardrobeAnalyticsData } from './types';

interface CategoryTabProps {
  analytics: WardrobeAnalyticsData;
}

export function CategoryTab({ analytics }: CategoryTabProps) {
  return (
    <TabsContent value="category" className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>カテゴリ分布</CardTitle>
          <CardDescription>
            各カテゴリの服数と着用状況
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={analytics?.categoryBreakdown || []}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ category, percentage }) =>
                    `${formatCategory(category)} (${percentage}%)`
                  }
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="count"
                >
                  {(analytics?.categoryBreakdown || []).map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={CHART_COLORS[index % CHART_COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0];
                      return (
                        <div className="bg-white p-2 border rounded shadow">
                          <p>{formatCategory(data.payload.category)}: {formatNumber(data.value)} 着</p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-6 space-y-2">
            {(analytics?.categoryBreakdown || []).map((category, index) => (
              <div
                key={category.category}
                className="flex items-center justify-between"
              >
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{
                      backgroundColor:
                        CHART_COLORS[index % CHART_COLORS.length],
                    }}
                  />
                  <span className="font-medium">{getCategoryLabel(category.category)}</span>
                </div>
                <div className="flex items-center gap-4 text-sm">
                  <span>{formatNumber(category.count)} 着</span>
                  <span className="text-gray-500">
                    {formatNumber(category.wearCount)} 回
                  </span>
                  <span className="text-gray-500">
                    {category.costPerWear > 0 ? `${formatCurrency(category.costPerWear)}/回` : 'データなし'}
                  </span>
                  <span className="font-medium">
                    {formatCurrency(category.value)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </TabsContent>
  );
}
