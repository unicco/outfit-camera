import React from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { X } from 'lucide-react';
import {
  WARDROBE_CATEGORIES,
  WARDROBE_SUBCATEGORIES,
  WARDROBE_SEASONS,
  WARDROBE_STATUSES,
  getCategoryLabel,
  getSeasonLabel,
  getStatusLabel,
} from '@/constants/wardrobe';

export interface FilterState {
  category: string;
  subcategory: string;
  season: string;
  tag: string;
  status: string;
}

interface WardrobeFiltersProps {
  filters: FilterState;
  availableTags: string[];
  onFilterChange: (filters: FilterState) => void;
}

export const WardrobeFilters: React.FC<WardrobeFiltersProps> = ({
  filters,
  availableTags,
  onFilterChange,
}) => {
  const handleFilterChange = <K extends keyof FilterState>(
    key: K,
    value: FilterState[K]
  ) => {
    const newFilters = { ...filters, [key]: value };

    // サブカテゴリをリセット（カテゴリが変更された場合）
    if (key === 'category' && value !== filters.category) {
      newFilters.subcategory = '';
    }

    onFilterChange(newFilters);
  };

  const clearFilter = (key: keyof FilterState) => {
    const newFilters = { ...filters, [key]: '' };

    // カテゴリをクリアした場合、サブカテゴリもクリア
    if (key === 'category') {
      newFilters.subcategory = '';
    }

    onFilterChange(newFilters);
  };

  const activeFiltersCount = Object.values(filters).filter(v => v !== '').length;

  // 選択中のカテゴリに基づくサブカテゴリリストを取得
  const availableSubcategories = filters.category
    ? WARDROBE_SUBCATEGORIES[filters.category] || []
    : [];

  return (
    <div className="space-y-4 p-4 bg-gray-50">
      {/* フィルタタイトル */}
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-sm text-gray-700">
          フィルタ
          {activeFiltersCount > 0 && (
            <span className="ml-2 text-xs text-gray-500">
              ({activeFiltersCount} 件)
            </span>
          )}
        </h3>
      </div>

      {/* フィルタコントロール */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* カテゴリ > サブカテゴリ */}
        <div className="col-span-2 md:col-span-1 space-y-2">
          <Select
            value={filters.category}
            onValueChange={(value) => handleFilterChange('category', value)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="カテゴリ" />
            </SelectTrigger>
            <SelectContent>
              {WARDROBE_CATEGORIES.map(category => (
                <SelectItem key={category.value} value={category.value}>
                  {category.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* サブカテゴリ（カテゴリが選択されている場合のみ表示） */}
          {filters.category && availableSubcategories.length > 0 && (
            <Select
              value={filters.subcategory}
              onValueChange={(value) => handleFilterChange('subcategory', value)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="サブカテゴリ" />
              </SelectTrigger>
              <SelectContent>
                {availableSubcategories.map(subcategory => (
                  <SelectItem key={subcategory} value={subcategory}>
                    {subcategory}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* 季節 */}
        <div>
          <Select
            value={filters.season}
            onValueChange={(value) => handleFilterChange('season', value)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="季節" />
            </SelectTrigger>
            <SelectContent>
              {WARDROBE_SEASONS.map(season => (
                <SelectItem key={season.value} value={season.value}>
                  {season.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* タグ */}
        <div>
          <Select
            value={filters.tag}
            onValueChange={(value) => handleFilterChange('tag', value)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="タグ" />
            </SelectTrigger>
            <SelectContent>
              {availableTags.map(tag => (
                <SelectItem key={tag} value={tag}>
                  {tag}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* ステータス */}
        <div>
          <Select
            value={filters.status}
            onValueChange={(value) => handleFilterChange('status', value)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="ステータス" />
            </SelectTrigger>
            <SelectContent>
              {WARDROBE_STATUSES.map(status => (
                <SelectItem key={status.value} value={status.value}>
                  {status.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* アクティブフィルタの表示 */}
      {activeFiltersCount > 0 && (
        <div className="flex flex-wrap gap-2">
          {filters.category && (
            <Badge variant="secondary" className="flex items-center gap-1">
              カテゴリ: {getCategoryLabel(filters.category)}
              {filters.subcategory && ` > ${filters.subcategory}`}
              <X
                className="w-3 h-3 ml-1 cursor-pointer"
                onClick={() => clearFilter('category')}
                aria-label="カテゴリフィルタをクリア"
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && clearFilter('category')}
              />
            </Badge>
          )}
          {filters.season && (
            <Badge variant="secondary" className="flex items-center gap-1">
              季節: {getSeasonLabel(filters.season)}
              <X
                className="w-3 h-3 ml-1 cursor-pointer"
                onClick={() => clearFilter('season')}
                aria-label="季節フィルタをクリア"
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && clearFilter('season')}
              />
            </Badge>
          )}
          {filters.tag && (
            <Badge variant="secondary" className="flex items-center gap-1">
              タグ: {filters.tag}
              <X
                className="w-3 h-3 ml-1 cursor-pointer"
                onClick={() => clearFilter('tag')}
                aria-label="タグフィルタをクリア"
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && clearFilter('tag')}
              />
            </Badge>
          )}
          {filters.status && (
            <Badge variant="secondary" className="flex items-center gap-1">
              ステータス: {getStatusLabel(filters.status)}
              <X
                className="w-3 h-3 ml-1 cursor-pointer"
                onClick={() => clearFilter('status')}
                aria-label="ステータスフィルタをクリア"
                role="button"
                tabIndex={0}
                onKeyDown={e => e.key === 'Enter' && clearFilter('status')}
              />
            </Badge>
          )}
        </div>
      )}
    </div>
  );
};
