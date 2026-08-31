import React, { useState, useEffect, useMemo } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Package, Search } from 'lucide-react';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import { getBestImageUrl } from '@/utils/imageUtils';
import { getCategoryLabel } from '@/constants/wardrobe';
import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';

export interface ClothingFilterItem {
  id: string;
  name: string;
  category?: string;
  brand?: string;
  imageUrls?: ExtendedClothingItem['imageUrls'];
}

interface ClothingItemFilterPickerProps {
  open: boolean;
  apiUrl: string;
  onSelect: (item: ClothingFilterItem) => void;
  onClose: () => void;
}

// カレンダーを「この服を着た日」で絞り込むための服選択モーダル
export const ClothingItemFilterPicker: React.FC<
  ClothingItemFilterPickerProps
> = ({ open, apiUrl, onSelect, onClose }) => {
  const [items, setItems] = useState<ExtendedClothingItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!open || items.length > 0) return;
    let cancelled = false;
    const fetchItems = async () => {
      setLoading(true);
      try {
        const data =
          await apiClient.get<ExtendedClothingItem[]>('/api/v2/wardrobe/items');
        if (cancelled) return;
        // 処分済は後ろに並べる（着用履歴の振り返りでは残す）
        const sorted = [...data].sort((a, b) => {
          const aDisposed = a.status === 'DISPOSED' ? 1 : 0;
          const bDisposed = b.status === 'DISPOSED' ? 1 : 0;
          return aDisposed - bDisposed;
        });
        setItems(sorted);
      } catch (error) {
        logger.error('Failed to fetch wardrobe items for filter:', error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchItems();
    return () => {
      cancelled = true;
    };
  }, [open, items.length]);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(item => {
      const name = (item.name || '').toLowerCase();
      const brand = (item.brand || '').toLowerCase();
      const category = getCategoryLabel(item.category).toLowerCase();
      return (
        name.includes(q) || brand.includes(q) || category.includes(q)
      );
    });
  }, [items, query]);

  return (
    <Dialog open={open} onOpenChange={isOpen => !isOpen && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>服で絞り込む</DialogTitle>
          <DialogDescription>
            服を選ぶと、その服を着た日がカレンダー上で強調表示されます
          </DialogDescription>
        </DialogHeader>

        {/* 検索 */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="名前・ブランド・カテゴリで検索"
            className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
          />
        </div>

        {/* 一覧 */}
        <div className="max-h-80 overflow-y-auto -mx-2 px-2">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="text-center py-10 text-gray-500 text-sm">
              該当する服がありません
            </div>
          ) : (
            <ul className="space-y-1">
              {filteredItems.map(item => {
                const imageUrl = getBestImageUrl(item.imageUrls, apiUrl, true);
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() =>
                        onSelect({
                          id: item.id,
                          name: item.name,
                          category: item.category,
                          brand: item.brand,
                          imageUrls: item.imageUrls,
                        })
                      }
                      className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-gray-100 transition-colors text-left"
                    >
                      <div className="w-12 h-12 flex-shrink-0 rounded-md overflow-hidden bg-gray-100 flex items-center justify-center">
                        {imageUrl ? (
                          <img
                            src={imageUrl}
                            alt={item.name}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <Package className="w-5 h-5 text-gray-400" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">
                          {item.name || getCategoryLabel(item.category)}
                        </p>
                        <p className="text-xs text-gray-500 truncate">
                          {[getCategoryLabel(item.category), item.brand]
                            .filter(Boolean)
                            .join(' ・ ')}
                        </p>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
