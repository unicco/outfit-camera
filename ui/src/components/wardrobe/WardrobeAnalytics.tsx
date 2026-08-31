import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { PieChart as PieChartIcon, BarChart3 } from 'lucide-react';
import { useWardrobeAnalytics } from './analytics/useWardrobeAnalytics';
import { OverviewCards } from './analytics/OverviewCards';
import { RankingsTab } from './analytics/RankingsTab';
import { CategoryTab } from './analytics/CategoryTab';
import { WearFrequencyTab } from './analytics/WearFrequencyTab';
import { CostTab } from './analytics/CostTab';
import { SeasonTab } from './analytics/SeasonTab';
import { BrandTab } from './analytics/BrandTab';
import { MatrixTab } from './analytics/MatrixTab';

export function WardrobeAnalytics() {
  const {
    analytics,
    rankings,
    categorySeasonMatrix,
    loading,
    error,
    timeRange,
    setTimeRange,
    selectedCategory,
    setSelectedCategory,
    selectedStatus,
    setSelectedStatus,
  } = useWardrobeAnalytics();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <BarChart3 className="h-12 w-12 mx-auto text-gray-400 animate-pulse mb-4" />
          <p className="text-gray-500">分析データを読み込み中...</p>
        </div>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="text-center py-12">
        <PieChartIcon className="h-16 w-16 mx-auto text-gray-400 mb-4" />
        <p className="text-gray-500 text-lg">分析データがありません</p>
      </div>
    );
  }

  return (
    <div className="flex-1 bg-gray-50 overflow-y-auto">
      <div className="p-6 lg:p-8">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Error Alert */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
              <p className="text-red-800 flex items-center gap-2">
                <span className="text-red-600">⚠️</span>
                {error}
              </p>
            </div>
          )}

          {/* Time Range Selector */}
          <div className="flex justify-end">
            <Select value={timeRange} onValueChange={setTimeRange}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="期間を選択" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全期間</SelectItem>
                <SelectItem value="year">過去 1 年</SelectItem>
                <SelectItem value="6months">過去 6 ヶ月</SelectItem>
                <SelectItem value="3months">過去 3 ヶ月</SelectItem>
                <SelectItem value="month">過去 1 ヶ月</SelectItem>
              </SelectContent>
            </Select>
          </div>

      {/* Overview Cards */}
      <OverviewCards analytics={analytics} />

      {/* Analytics Tabs */}
      <Tabs defaultValue="rankings" className="space-y-4">
        <TabsList className="flex flex-wrap justify-start gap-1 h-auto p-1">
          <TabsTrigger value="rankings" className="data-[state=active]:bg-white">ランキング</TabsTrigger>
          <TabsTrigger value="category" className="data-[state=active]:bg-white">カテゴリ</TabsTrigger>
          <TabsTrigger value="wear" className="data-[state=active]:bg-white">着用頻度</TabsTrigger>
          <TabsTrigger value="cost" className="data-[state=active]:bg-white">コスト</TabsTrigger>
          <TabsTrigger value="season" className="data-[state=active]:bg-white">シーズン</TabsTrigger>
          <TabsTrigger value="brand" className="data-[state=active]:bg-white">ブランド</TabsTrigger>
          <TabsTrigger value="matrix" className="data-[state=active]:bg-white">カテゴリ × 季節</TabsTrigger>
        </TabsList>

        <RankingsTab
          rankings={rankings}
          selectedCategory={selectedCategory}
          setSelectedCategory={setSelectedCategory}
          selectedStatus={selectedStatus}
          setSelectedStatus={setSelectedStatus}
        />

        <CategoryTab analytics={analytics} />

        <WearFrequencyTab analytics={analytics} />

        <CostTab analytics={analytics} />

        <SeasonTab analytics={analytics} />

        <BrandTab analytics={analytics} />

        <MatrixTab categorySeasonMatrix={categorySeasonMatrix} />
      </Tabs>
        </div>
      </div>
    </div>
  );
}
