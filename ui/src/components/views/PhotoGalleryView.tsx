import { NewItemRegistrationPage } from '@/components/wardrobe/NewItemRegistrationPage';
import { EnhancedPhotoClothingSelection } from '@/components/wardrobe/EnhancedPhotoClothingSelection';
import { FullBodyPhotoUpload } from '@/components/upload';
import type { ViewMode } from '@/types/app';
import type { OutfitRecord } from '@/types/outfit';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import { logger } from '@/utils/logger';

interface PhotoGalleryViewProps {
  viewMode: ViewMode;
  animationClass: string;
  apiUrl: string;
  selectedPhotoForOutfit: OutfitRecord | null;
  selectedDateForRegistration: Date | null;
  showMessage: (text: string, type?: 'success' | 'error') => void;
  setViewModeWithAnimation: (mode: ViewMode, animation?: string) => void;
  setViewModeWithContext: (
    mode: ViewMode,
    animation?: string,
    previousContext?: {
      viewMode: ViewMode;
      selectedPhotoForOutfit?: OutfitRecord | null;
      selectedClothingItem?: ExtendedClothingItem | null;
    }
  ) => void;
  setSelectedPhotoForOutfit: (photo: OutfitRecord | null) => void;
  setAnimationClass: (className: string) => void;
  setOutfitRefreshTrigger: (
    trigger: number | ((prev: number) => number)
  ) => void;
  fetchRecords: () => void;
  onOutfitSaved?: (recordedDate?: string) => void;
}

export const PhotoGalleryView = ({
  viewMode,
  animationClass,
  apiUrl,
  selectedPhotoForOutfit,
  selectedDateForRegistration,
  showMessage,
  setViewModeWithAnimation,
  setViewModeWithContext,
  setSelectedPhotoForOutfit,
  setAnimationClass,
  setOutfitRefreshTrigger,
  fetchRecords,
  onOutfitSaved,
}: PhotoGalleryViewProps) => {
  if (viewMode === 'wardrobe-register') {
    return (
      <div className="animate-slide-in-right">
        <NewItemRegistrationPage
          apiUrl={apiUrl}
          onClose={() => setViewModeWithAnimation('wardrobe')}
          onSuccess={() => {
            setViewModeWithAnimation('wardrobe');
          }}
          onShowMessage={showMessage}
        />
      </div>
    );
  }

  if (viewMode === 'photo-clothing-selection') {
    return (
      <div className={animationClass}>
        <EnhancedPhotoClothingSelection
          photo={{
            id: selectedPhotoForOutfit?.photoId || '',
            filename: '',
            filePath: '',
            photoUrl: selectedPhotoForOutfit?.photoUrl,
            createdAt: selectedPhotoForOutfit?.recordedAt || '',
            updatedAt: selectedPhotoForOutfit?.recordedAt || '',
          }}
          onBack={() => {
            // ワードローブ選択画面からカレンダーに移動する際にコンテキストを保存
            setViewModeWithContext('list', 'animate-slide-in-left', {
              viewMode: 'photo-clothing-selection',
              selectedPhotoForOutfit: selectedPhotoForOutfit,
            });
            setSelectedPhotoForOutfit(null);
            setAnimationClass('');
          }}
          onSaveComplete={(message, recordedDate) => {
            logger.dev(
              '[PhotoGalleryView] onSaveComplete called with message:',
              message,
              'recordedDate:',
              recordedDate
            );
            setSelectedPhotoForOutfit(null);
            showMessage(message, 'success');

            // OutfitCalendarに記録した日付を通知
            if (recordedDate) {
              // グローバル関数経由でOutfitCalendarに通知
              if ((window as Window & { __outfitCalendarSaved?: (date: string) => void }).__outfitCalendarSaved) {
                (window as Window & { __outfitCalendarSaved?: (date: string) => void }).__outfitCalendarSaved(recordedDate);
              }

              if (onOutfitSaved) {
                onOutfitSaved(recordedDate);
              }
            }

            setViewModeWithAnimation('list', 'animate-slide-in-left');
            logger.dev('[PhotoGalleryView] Setting outfit refresh trigger');
            setOutfitRefreshTrigger(prev => {
              const newValue = prev + 1;
              logger.dev(
                '[PhotoGalleryView] Outfit refresh trigger updated:',
                prev,
                '->',
                newValue
              );
              return newValue;
            });
            logger.dev('[PhotoGalleryView] Calling fetchRecords');
            fetchRecords();
          }}
        />
      </div>
    );
  }

  if (viewMode === 'upload') {
    return (
      <div className={animationClass}>
        <FullBodyPhotoUpload
          apiUrl={apiUrl}
          selectedDate={selectedDateForRegistration}
          onSuccess={message => {
            showMessage(message, 'success');
            fetchRecords();
          }}
          onBack={() =>
            setViewModeWithAnimation('list', 'animate-slide-in-left')
          }
        />
      </div>
    );
  }

  return null;
};
