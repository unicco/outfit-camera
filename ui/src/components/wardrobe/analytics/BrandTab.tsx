import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { TabsContent } from '@/components/ui/tabs';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { formatNumber } from '@/utils/numberUtils';
import { CHART_COLORS } from './analyticsTransforms';
import type { WardrobeAnalyticsData } from './types';

interface BrandTabProps {
  analytics: WardrobeAnalyticsData;
}

export function BrandTab({ analytics }: BrandTabProps) {
  return (
    <TabsContent value="brand" className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>ブランド分布</CardTitle>
          <CardDescription>保有服のブランド別内訳</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={analytics?.brandDistribution || []}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ brand, percentage }) =>
                    `${brand || 'ノーブランド'} (${percentage}%)`
                  }
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="count"
                >
                  {(analytics?.brandDistribution || []).map((_, index) => (
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
                          <p>{data.payload.brand || 'ノーブランド'}: {formatNumber(data.value)} 着</p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

    </TabsContent>
  );
}
