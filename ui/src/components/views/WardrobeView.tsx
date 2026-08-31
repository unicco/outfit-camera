import { useState, type Dispatch, type SetStateAction } from 'react';
import { Button } from '@/components/ui/button';
import { WardrobeAnalytics } from '@/components/wardrobe/WardrobeAnalytics';
import { WardrobeGrid } from '@/components/wardrobe/WardrobeGrid';
import { NewItemRegistration } from '@/components/wardrobe/NewItemRegistration';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import type { ViewMode } from '@/types/app';
import type { FilterState } from '@/components/wardrobe/WardrobeFilters';

interface WardrobeViewProps {
  apiUrl: string;
  animationClass: string;
  viewMode: ViewMode;
  showWardrobeAnalytics: boolean;
  showNewItemDialog: boolean;
  setShowWardrobeAnalytics: (show: boolean) => void;
  setShowNewItemDialog: (show: boolean) => void;
  setSelectedClothingItem: (item: ExtendedClothingItem) => void;
  setViewMode: (mode: ViewMode) => void;
  filters: FilterState;
  setFilters: Dispatch<SetStateAction<FilterState>>;
  showDisposedItems: boolean;
  setShowDisposedItems: Dispatch<SetStateAction<boolean>>;
  showListedItems: boolean;
  setShowListedItems: Dispatch<SetStateAction<boolean>>;
}

export const WardrobeView = ({
  apiUrl,
  animationClass,
  // viewMode: unused parameter kept for interface compatibility
  showWardrobeAnalytics,
  showNewItemDialog,
  setShowWardrobeAnalytics,
  setShowNewItemDialog,
  setSelectedClothingItem,
  setViewMode,
  filters,
  setFilters,
  showDisposedItems,
  setShowDisposedItems,
  showListedItems,
  setShowListedItems,
}: WardrobeViewProps) => {
  const [refreshKey, setRefreshKey] = useState(0);

  const refreshWardrobeData = () => {
    setRefreshKey(prev => prev + 1);
  };

  return (
    <main
      className={`p-0 md:p-8 transition-all duration-500 ease-in-out ${animationClass}`}
    >
      <div className="max-w-7xl mx-auto">
        {/* Show analytics if toggled */}
        {showWardrobeAnalytics ? (
          <div className="space-y-6 p-4 md:p-0">
            <div className="flex items-center justify-end">
              <Button
                onClick={() => setShowWardrobeAnalytics(false)}
                variant="outline"
              >
                ダッシュボードに戻る
              </Button>
            </div>
            <WardrobeAnalytics />
          </div>
        ) : (
          <div className="space-y-6 p-4 md:p-0">
            {/* Wardrobe Header */}
            {/* Removed page title section as per requirements */}
            <WardrobeGrid
              key={refreshKey}
              apiUrl={apiUrl}
              onItemClick={item => {
                setSelectedClothingItem(item);
                setViewMode('wardrobe-detail');
              }}
              onAddNew={() => setViewMode('wardrobe-register')}
              filters={filters}
              setFilters={setFilters}
              showDisposedItems={showDisposedItems}
              setShowDisposedItems={setShowDisposedItems}
              showListedItems={showListedItems}
              setShowListedItems={setShowListedItems}
            />
          </div>
        )}

        {/* New Item Registration Dialog */}
        {showNewItemDialog && (
          <NewItemRegistration
            open={showNewItemDialog}
            onOpenChange={setShowNewItemDialog}
            apiUrl={apiUrl}
            onSuccess={() => {
              setShowNewItemDialog(false);
              refreshWardrobeData();
            }}
          />
        )}
      </div>
    </main>
  );
};
