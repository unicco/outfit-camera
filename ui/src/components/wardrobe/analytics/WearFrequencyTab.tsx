import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { TabsContent } from '@/components/ui/tabs';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts';
import { formatNumber } from '@/utils/numberUtils';
import { getWearFrequencyChartData } from './analyticsTransforms';
import type { WardrobeAnalyticsData } from './types';

interface WearFrequencyTabProps {
  analytics: WardrobeAnalyticsData;
}

export function WearFrequencyTab({ analytics }: WearFrequencyTabProps) {
  return (
    <TabsContent value="wear" className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>着用頻度</CardTitle>
          <CardDescription>各月の着用回数の推移</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={getWearFrequencyChartData(analytics?.wearFrequency)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="bg-white p-2 border rounded shadow">
                          <p className="font-medium">{label}</p>
                          <p className="text-blue-600">着用: {formatNumber(payload[0].value)} 回</p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="wearCount"
                  stroke="#3B82F6"
                  fill="#3B82F6"
                  fillOpacity={0.3}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </TabsContent>
  );
}
