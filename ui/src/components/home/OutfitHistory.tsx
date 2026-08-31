import React from 'react';
import { OutfitCalendar } from './OutfitCalendar';
import { dateUtils } from '@/utils/dateUtils';
import type { OutfitRecord } from '@/types/outfit';

interface PhotoRecord {
  id: string;
  filename: string;
  capturedAt: string;
  personDetected: boolean;
  confidenceScore?: number;
  clothingItems?: string[];
  source: string;
  aiDetectionStatus?: string;
  aiDetectionResults?: Record<string, unknown>;
  aiAnnotationImageUrl?: string;
  aiCroppedImages?: string[];
  photoUrl?: string;  // GCS URL を追加
}

interface OutfitHistoryProps {
  apiUrl: string;
  onPhotoSelect?: (record: OutfitRecord) => void;
  onRegisterFullBody?: (date: Date) => void;
  onOutfitSaved?: (recordedDate?: string) => void;
  outfitRefreshTrigger?: number;
  goBack?: () => void;
  initialMonth?: Date | null;
  onMonthChange?: (month: Date) => void;
}

export const OutfitHistory: React.FC<OutfitHistoryProps> = ({
  apiUrl,
  onPhotoSelect,
  onRegisterFullBody,
  onOutfitSaved,
  outfitRefreshTrigger,
  goBack,
  initialMonth,
  onMonthChange,
}) => {

  const refreshTrigger = outfitRefreshTrigger ?? 0;

  const handlePhotoSelect = (photos: PhotoRecord[], date: Date) => {
    if (photos.length === 0) {
      // 写真がない日付の場合、直接ワードローブ選択画面に遷移
      handleDateWithoutPhoto(date);
    } else {
      // 写真がある場合も直接ワードローブ選択画面に遷移（最初の写真を使用）
      handleDirectClothingSelection(photos[0], date);
    }
  };

  const handleDateWithoutPhoto = (date: Date) => {
    // 写真がない日付用のダミーレコードを作成してワードローブ選択画面に送る
    // JST正午のDateオブジェクトを作成してタイムゾーン問題を回避
    const localDateStr = dateUtils.jstToDateString(date);
    const jstNoonDate = dateUtils.parseDateAsJSTNoon(localDateStr);
    const localIsoString = jstNoonDate.toISOString();

    const dummyRecord = {
      id: `manual-${localDateStr}`,
      photoId: '',
      recordedAt: localIsoString,
      manualSelection: true,
      createdAt: localIsoString,
      updatedAt: localIsoString,
      outfitItems: [],
    };

    if (onPhotoSelect) {
      onPhotoSelect(dummyRecord);
    }
  };

  const handleDirectClothingSelection = (photo: PhotoRecord, date: Date) => {
    // 写真がある場合の服を選択画面への遷移
    // JST正午のDateオブジェクトを作成してタイムゾーン問題を回避
    const localDateStr = dateUtils.jstToDateString(date);
    const jstNoonDate = dateUtils.parseDateAsJSTNoon(localDateStr);
    const localIsoString = jstNoonDate.toISOString();

    const legacyRecord = {
      id: photo.id,
      photoId: photo.id,
      photoUrl: photo.photoUrl,
      recordedAt: localIsoString,
      manualSelection: false,
      createdAt: localIsoString,
      updatedAt: localIsoString,
      outfitItems: (photo.clothingItems || []).map(item => ({
        id: `${photo.id}-${item}`,
        outfitRecordId: photo.id,
        clothingItemId: item,
        manualAdded: false,
        createdAt: localIsoString,
      })),
    };

    if (onPhotoSelect) {
      onPhotoSelect(legacyRecord);
    }
  };

  return (
    <div className="space-y-4">
      <OutfitCalendar
        apiUrl={apiUrl}
        onPhotoSelect={handlePhotoSelect}
        onRegisterFullBody={onRegisterFullBody}
        refreshTrigger={refreshTrigger}
        goBack={goBack}
        onOutfitSaved={onOutfitSaved}
        initialMonth={initialMonth}
        onMonthChange={onMonthChange}
      />
    </div>
  );
};
