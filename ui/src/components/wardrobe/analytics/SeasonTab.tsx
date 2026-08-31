import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { formatNumber } from '@/utils/numberUtils';
import { formatSeason } from './analyticsTransforms';
import { getSeasonIcon } from './analyticsFormatters';
import type { WardrobeAnalyticsData } from './types';

interface SeasonTabProps {
  analytics: WardrobeAnalyticsData;
}

export function SeasonTab({ analytics }: SeasonTabProps) {
  return (
    <TabsContent value="season" className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>シーズン分析</CardTitle>
          <CardDescription>各シーズンの服数と着用率</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {(analytics?.seasonalUsage || []).map(season => (
              <Card
                key={season.season}
                className="bg-gradient-to-br from-gray-50 to-gray-100"
              >
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium">
                      {formatSeason(season.season)}
                    </span>
                    {getSeasonIcon(season.season)}
                  </div>
                  <div className="space-y-1">
                    <p className="text-2xl font-bold">
                      {formatNumber(season.itemCount)}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <Badge variant="outline" className="text-xs">
                        {formatNumber(season.wearCount)} 回着用
                      </Badge>
                    </div>
                    <div className="mt-2">
                      <div className="text-xs text-gray-600">
                        平均: {season.wearCount > 0 ? (season.wearCount / season.itemCount).toFixed(1) : '0.0'} 回/服
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
    </TabsContent>
  );
}
