import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  type Dispatch,
  type SetStateAction,
} from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Eye,
  Calendar,
  Plus,
  AlertTriangle,
  Store,
  Archive,
} from 'lucide-react';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import { getBestImageUrl } from '@/utils/imageUtils';
import { getCategorySubcategoryDisplay } from '@/constants/wardrobe';
import { apiClient } from '@/services/apiClient';
import { WardrobeFilters, type FilterState } from './WardrobeFilters';
import { logger } from '@/utils/logger';
import { formatNumber } from '@/utils/numberUtils';

interface WardrobeGridProps {
  apiUrl: string;
  onItemClick?: (item: ExtendedClothingItem) => void;
  onAddNew?: () => void;
  filters: FilterState;
  setFilters: Dispatch<SetStateAction<FilterState>>;
  showDisposedItems: boolean;
  setShowDisposedItems: Dispatch<SetStateAction<boolean>>;
  showListedItems: boolean;
  setShowListedItems: Dispatch<SetStateAction<boolean>>;
}

export const WardrobeGrid: React.FC<WardrobeGridProps> = ({
  apiUrl,
  onItemClick,
  onAddNew,
  filters,
  setFilters,
  showDisposedItems,
  setShowDisposedItems,
  showListedItems,
  setShowListedItems,
}) => {
  const [items, setItems] = useState<ExtendedClothingItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Check URL parameter for showing disposed items on mount
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const showDisposedFromUrl = urlParams.get('showDisposed') === 'true';
    const showListedFromUrl = urlParams.get('showListed') === 'true';
    if (showDisposedFromUrl && !showDisposedItems) {
      setShowDisposedItems(true);
    }
    if (showListedFromUrl && !showListedItems) {
      setShowListedItems(true);
    }
  }, [showDisposedItems, showListedItems, setShowDisposedItems, setShowListedItems]);

  const fetchItems = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiClient.get<ExtendedClothingItem[]>('/api/v2/wardrobe/items');
      const statusPriority = (status?: string) => (status === 'DISPOSED' ? 1 : 0);
      // Sort by status (disposed last) and createdAt descending
      const sortedData = data.sort((a, b) => {
        const statusDiff = statusPriority(a.status) - statusPriority(b.status);
        if (statusDiff !== 0) {
          return statusDiff;
        }
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      });
      setItems(sortedData);
    } catch (error) {
      logger.error('Error fetching wardrobe items:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- マウント時のワードローブ取得（fetchItems 内部で setState）
    fetchItems();
  }, [fetchItems]);

  // Get unique tags from all items
  const availableTags = useMemo(() => {
    const tagSet = new Set<string>();
    items.forEach(item => {
      if (item.tags && Array.isArray(item.tags)) {
        item.tags.forEach(tag => tagSet.add(tag));
      }
    });
    return Array.from(tagSet).sort();
  }, [items]);

  // フィルタリングロジックを分離して最適化
  const applyFilters = useCallback((item: ExtendedClothingItem) => {
    // Apply filters
    if (filters.category) {
      // カテゴリは大文字小文字を考慮しない比較
      if (item.category?.toLowerCase() !== filters.category.toLowerCase()) return false;
    }
    if (filters.subcategory && item.subcategory !== filters.subcategory) return false;
    if (filters.season && (!item.season || !Array.isArray(item.season) || !item.season.includes(filters.season))) return false;
    if (filters.tag && (!item.tags || !Array.isArray(item.tags) || !item.tags.includes(filters.tag))) return false;
    if (filters.status) {
      const itemStatus = item.status || 'ACTIVE';
      if (itemStatus !== filters.status) return false;
    }
    return true;
  }, [filters]);

  // Filter items based on showDisposedItems/showListedItems state and filters
  const filteredItems = useMemo(() => {
    return items.filter(item => {
      // First filter by disposed/listed status
      if (showDisposedItems) {
        if (item.status !== 'DISPOSED') return false;
      } else if (showListedItems) {
        if (item.status !== 'SELLING') return false;
      } else {
        // Hide both disposed and selling items by default
        if (item.status === 'DISPOSED' || item.status === 'SELLING') return false;
      }

      return applyFilters(item);
    });
  }, [items, showDisposedItems, showListedItems, applyFilters]);

  // Count disposed and listed items for buttons
  const disposedItemsCount = items.filter(
    item => item.status === 'DISPOSED'
  ).length;

  const listedItemsCount = items.filter(
    item => item.status === 'SELLING'
  ).length;

  return (
    <div className="space-y-4">
      {/* Items Grid */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-0 sm:gap-4 -mx-4 sm:mx-0">
          {filteredItems.map(item => (
            <ItemCard
              key={item.id}
              item={item}
              onClick={() => onItemClick?.(item)}
              apiUrl={apiUrl}
            />
          ))}
          {!showDisposedItems && onAddNew && (
            <AddNewItemCard onClick={onAddNew} />
          )}
        </div>
      )}

      {/* Show Disposed/Listed Items Buttons - Bottom */}
      <div className="flex gap-4 justify-center pt-4">
        {!showDisposedItems && !showListedItems && listedItemsCount > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setShowListedItems(true);
              const url = new URL(window.location.href);
              url.searchParams.set('showListed', 'true');
              window.history.replaceState({}, '', url);
            }}
            className="text-xs flex-1 max-w-[200px]"
          >
            <Store className="h-4 w-4 mr-1" />
            出品中 ({listedItemsCount}件)
          </Button>
        )}

        {!showDisposedItems && !showListedItems && disposedItemsCount > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setShowDisposedItems(true);
              const url = new URL(window.location.href);
              url.searchParams.set('showDisposed', 'true');
              window.history.replaceState({}, '', url);
            }}
            className="text-xs flex-1 max-w-[200px]"
          >
            <Archive className="h-4 w-4 mr-1" />
            処分済 ({disposedItemsCount}件)
          </Button>
        )}

        {(showListedItems || showDisposedItems) && (
          <Button
            variant="default"
            size="sm"
            onClick={() => {
              setShowListedItems(false);
              setShowDisposedItems(false);
              // Clear URL parameters
              const url = new URL(window.location.href);
              url.searchParams.delete('showListed');
              url.searchParams.delete('showDisposed');
              window.history.replaceState({}, '', url);
            }}
            className="text-xs"
          >
            戻る
          </Button>
        )}
      </div>

      {/* Filters section - Bottom */}
      <WardrobeFilters
        filters={filters}
        availableTags={availableTags}
        onFilterChange={setFilters}
      />
    </div>
  );
};

interface AddNewItemCardProps {
  onClick: () => void;
}

const AddNewItemCard: React.FC<AddNewItemCardProps> = ({ onClick }) => {
  return (
    <Card
      variant="bordered"
      padding="none"
      className="overflow-hidden hover:shadow-lg transition-all cursor-pointer group rounded-none border-dashed border-2 border-gray-300 bg-gray-50/50 hover:bg-gray-100/50"
      onClick={onClick}
    >
      <div className="aspect-square bg-gradient-to-br from-gray-50 to-gray-100 flex flex-col items-center justify-center">
        <div className="w-12 h-12 rounded-full bg-blue-500 flex items-center justify-center mb-3 group-hover:bg-blue-600 transition-colors">
          <Plus className="w-6 h-6 text-white" />
        </div>
        <span className="text-sm font-medium text-gray-700 group-hover:text-gray-900 transition-colors">
          ワードローブを追加
        </span>
      </div>

      {/* Content - desktop only */}
      <CardContent className="p-4 hidden sm:block">
        <div className="text-center">
          <p className="text-xs text-gray-500 mt-1">クリックして追加</p>
        </div>
      </CardContent>
    </Card>
  );
};

interface ItemCardProps {
  item: ExtendedClothingItem;
  onClick?: () => void;
  apiUrl: string;
}

const ItemCard: React.FC<ItemCardProps> = ({ item, onClick, apiUrl }) => {
  const [, setImageLoaded] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);

  // Get status icon for disposal consideration and selling items
  const getStatusIcon = () => {
    switch (item.status) {
      case 'DISPOSAL_CONSIDERATION':
        return <AlertTriangle className="w-4 h-4 text-orange-500" />;
      case 'SELLING':
        return <Store className="w-4 h-4 text-blue-500" />;
      default:
        return null;
    }
  };

  const getStatusLabel = () => {
    switch (item.status) {
      case 'DISPOSAL_CONSIDERATION':
        return '処分検討中';
      case 'SELLING':
        return '出品中';
      default:
        return null;
    }
  };

  return (
    <div className="relative">
      <Card
        variant="bordered"
        padding="none"
        className="overflow-hidden hover:shadow-lg transition-all cursor-pointer group rounded-none"
        onClick={onClick}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        {/* Image */}
        <div className="aspect-square bg-gray-100 relative">
          {(() => {
            // Check for both array and dict formats
            const hasImages =
              item.imageUrls &&
              ((Array.isArray(item.imageUrls) && item.imageUrls.length > 0) ||
                (typeof item.imageUrls === 'object' &&
                  !Array.isArray(item.imageUrls) &&
                  item.imageUrls.original));

            if (!hasImages) return null;

            const imageUrl = getBestImageUrl(item.imageUrls, apiUrl, true);

            if (!imageUrl) return null;

            return (
              <img
                src={imageUrl}
                alt={item.category}
                className="w-full h-full object-cover"
                onLoad={() => {
                  setImageLoaded(true);
                }}
                onError={e => {
                  logger.error(
                    `❌ [GRID] [${item.name || item.category}] Image failed to load:`,
                    e.currentTarget.src
                  );
                  setImageLoaded(false);
                }}
              />
            );
          })()}


          {/* Status badge for disposal consideration and selling */}
          {(item.status === 'DISPOSAL_CONSIDERATION' ||
            item.status === 'SELLING') && (
            <div className="absolute top-2 right-2">
              <div className="bg-white/90 text-gray-800 px-2 py-1 rounded text-xs font-medium flex items-center gap-1 shadow-sm">
                {getStatusIcon()}
                {getStatusLabel()}
              </div>
            </div>
          )}

          {/* Overlay on hover - desktop only */}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors hidden sm:block">
            <div className="absolute bottom-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <Button
                size="sm"
                variant="secondary"
                className="bg-white/90 hover:bg-white"
                onClick={e => {
                  e.stopPropagation();
                  // Quick view action
                }}
              >
                <Eye className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Content - desktop only */}
        <CardContent className="p-4 hidden sm:block">
          <div className="space-y-2">
            {/* Brand Name */}
            <div>
              <h3 className="font-medium text-gray-900 line-clamp-1">
                {item.brand || 'ノーブランド'}
              </h3>
            </div>

            {/* Stats */}
            <div className="flex items-center justify-between text-sm text-gray-600 pt-2">
              <div className="flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" />
                <span>{formatNumber(item.wearCount || 0)}</span>
              </div>
              {item.costPerWear && (
                <div className="flex items-center gap-1">
                  <span>¥{formatNumber(Math.round(item.costPerWear))}/回</span>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tooltip */}
      {showTooltip && (
        <div className="absolute z-50 bg-gray-900 text-white text-sm rounded-lg px-3 py-2 shadow-lg whitespace-nowrap top-2 left-2 transform">
          <div className="space-y-1">
            <div className="font-medium">
              {getCategorySubcategoryDisplay(item.category, item.subcategory)}
            </div>
            {item.purchaseLocation && (
              <div>
                <span className="font-medium">購入場所:</span>{' '}
                {item.purchaseLocation}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
