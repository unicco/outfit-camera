import { ClothingItemDetail } from '@/components/wardrobe/ClothingItemDetailSimple';
import { EditItemPage } from '@/components/wardrobe/EditItemPage';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import type { ViewMode } from '@/types/app';

interface WardrobeDetailViewProps {
  viewMode: ViewMode;
  selectedClothingItem: ExtendedClothingItem;
  apiUrl: string;
  showMessage: (text: string, type?: 'success' | 'error') => void;
  setSelectedClothingItem: (item: ExtendedClothingItem | null) => void;
  setViewModeWithAnimation: (mode: ViewMode, animation?: string) => void;
}

export const WardrobeDetailView = ({
  viewMode,
  selectedClothingItem,
  apiUrl,
  showMessage,
  setSelectedClothingItem,
  setViewModeWithAnimation,
}: WardrobeDetailViewProps) => {
  if (viewMode === 'wardrobe-detail') {
    return (
      <div className="animate-slide-in-right">
        <ClothingItemDetail
          item={selectedClothingItem}
          onClose={() => {
            setSelectedClothingItem(null);
            setViewModeWithAnimation('wardrobe', 'animate-slide-in-left');
          }}
          onEdit={() =>
            setViewModeWithAnimation('wardrobe-edit', 'animate-slide-in-right')
          }
          apiUrl={apiUrl}
        />
      </div>
    );
  }

  if (viewMode === 'wardrobe-edit') {
    return (
      <div className="animate-slide-in-right">
        <EditItemPage
          item={selectedClothingItem}
          apiUrl={apiUrl}
          onClose={() =>
            setViewModeWithAnimation('wardrobe-detail', 'animate-slide-in-left')
          }
          onSuccess={() => {
            setSelectedClothingItem(null);
            setViewModeWithAnimation('wardrobe', 'animate-slide-in-left');
            showMessage('ワードローブアイテムが更新されました！', 'success');
          }}
          onShowMessage={showMessage}
        />
      </div>
    );
  }

  return null;
};
