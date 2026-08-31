import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { ChevronLeft, ChevronRight, Camera, Plus, Shirt, X } from 'lucide-react';
import { OutfitItem } from '../../types/outfit';
import {
  ClothingItemFilterPicker,
  type ClothingFilterItem,
} from './ClothingItemFilterPicker';
import { getBestImageUrl } from '@/utils/imageUtils';
import { ExtendedClothingItem } from '@/types/wardrobe';
import type { ExternalRentalItem } from '@/types/externalRentals';
import {
  format,
  parseISO,
  startOfMonth,
  endOfMonth,
  eachDayOfInterval,
  isSameMonth,
  isToday,
  addMonths,
  subMonths,
  isSameDay,
  startOfWeek,
  endOfWeek,
} from 'date-fns';
import { ja } from 'date-fns/locale';
import { OutfitItemGrid } from './OutfitItemGrid';
import { dateUtils } from '@/utils/dateUtils';
import { apiClient } from '@/services/apiClient';
import { LazyImage } from '@/components/common/LazyImage';
import { logger } from '@/utils/logger';

// AI 検出ステータスとアイテム選択状況に応じたカメラアイコンの色を取得
const getCameraIconColor = (
  photos: PhotoRecord[],
  outfitItems: OutfitItem[] = []
): string => {
  // 🔴 Issue #431 FIX: 写真がない場合のみグレー、ある場合は必ずアイコン表示
  if (!photos || photos.length === 0) return 'bg-gray-400'; // 写真なしはグレー

  // 手動でアイテムが選択されているか確認（写真のclothingItems/clothing_itemsまたはoutfitItemsで判定）
  // Issue #431: API互換性のため両方の命名をチェック
  const hasManualItems =
    photos.some(p => {
      const camelCaseItems = p.clothingItems && p.clothingItems.length > 0;
      const snakeCaseItems =
        (p as unknown as Record<string, unknown>).clothing_items &&
        (p as unknown as Record<string, unknown>).clothing_items &&
        Array.isArray(
          (p as unknown as Record<string, unknown>).clothing_items
        ) &&
        ((p as unknown as Record<string, unknown>).clothing_items as unknown[])
          .length > 0;
      return camelCaseItems || snakeCaseItems;
    }) || outfitItems.length > 0;

  // AI検出ステータス確認
  // Issue #431: API互換性のため両方の命名をチェック
  const statuses = photos.map(p => {
    const status =
      p.aiDetectionStatus ||
      (p as unknown as Record<string, unknown>).ai_detection_status ||
      'pending';
    return status;
  });

  // 優先度判定: failed > processing > pending with no items > completed/manual
  if (statuses.includes('failed') && !hasManualItems) return 'bg-red-500';
  if (statuses.includes('processing')) return 'bg-gray-400';

  // pendingでも手動でアイテムが選択されていれば青色（完了扱い）
  if (statuses.includes('pending')) {
    return hasManualItems ? 'bg-blue-500' : 'bg-gray-400';
  }

  return 'bg-blue-500'; // 写真ありは基本的に青で表示
};

interface PhotoRecord {
  id: string;
  filename: string;
  capturedAt: string;
  personDetected: boolean;
  confidenceScore?: number;
  clothingItems?: string[];
  source: string;
  aiDetectionStatus?: string;
  aiAnnotationImageUrl?: string;
  photoUrl?: string;  // GCS URL を追加
}

interface DailyPhotos {
  [dateKey: string]: PhotoRecord[];
}

interface DailyOutfits {
  [dateKey: string]: OutfitItem[];
}

interface OutfitCalendarProps {
  apiUrl: string;
  onPhotoSelect?: (photos: PhotoRecord[], date: Date) => void;
  onRegisterFullBody?: (date: Date) => void;
  refreshTrigger?: number; // Add trigger to refresh outfit data when outfits are saved
  goBack?: () => void; // Function to go back to previous screen
  onOutfitSaved?: (recordedDate?: string) => void; // Callback when outfit is saved
  initialMonth?: Date | null; // 詳細画面から戻ったときに復元する月
  onMonthChange?: (month: Date) => void; // 月が変わったときに親に通知
}

export const OutfitCalendar: React.FC<OutfitCalendarProps> = ({
  apiUrl,
  onPhotoSelect,
  onRegisterFullBody,
  refreshTrigger,
  goBack,
  onOutfitSaved,
  initialMonth,
  onMonthChange,
}) => {
  const [currentMonth, setCurrentMonth] = useState(initialMonth ?? new Date());
  const [dailyPhotos, setDailyPhotos] = useState<DailyPhotos>({});

  // マウント時に親に現在の月を通知（遷移時にコンテキストに保存するため）
  useEffect(() => { onMonthChange?.(currentMonth); }, [onMonthChange]);
  const [dailyOutfits, setDailyOutfits] = useState<DailyOutfits>({});
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [showDateDetail, setShowDateDetail] = useState(false);
  // スワイプ機能のための状態
  const [touchStart, setTouchStart] = useState<{ x: number; y: number } | null>(
    null
  );
  const [touchEnd, setTouchEnd] = useState<{ x: number; y: number } | null>(
    null
  );

  // 服フィルター: 選んだ服を着た日をカレンダー上で強調表示する
  const [showItemPicker, setShowItemPicker] = useState(false);
  const [filterItem, setFilterItem] = useState<ClothingFilterItem | null>(null);
  const [filterDates, setFilterDates] = useState<Set<string> | null>(null);
  const [filterLoading, setFilterLoading] = useState(false);

  const handleSelectFilterItem = useCallback(
    async (item: ClothingFilterItem) => {
      setShowItemPicker(false);
      setFilterItem(item);
      // 服を切り替えたとき、fetch 完了まで前の服の着用日が残らないようクリアする
      setFilterDates(null);
      setFilterLoading(true);
      try {
        const res = await apiClient.get<{
          wearHistory?: { date: string | null }[];
        }>(`/api/v2/wardrobe/items/${item.id}/wear-history`);
        const dates = new Set<string>();
        (res.wearHistory || []).forEach(w => {
          if (w.date) dates.add(w.date);
        });
        setFilterDates(dates);
      } catch (error) {
        logger.error('Failed to fetch wear history for filter:', error);
        setFilterDates(new Set());
      } finally {
        setFilterLoading(false);
      }
    },
    []
  );

  const clearFilter = useCallback(() => {
    setFilterItem(null);
    setFilterDates(null);
  }, []);

  const isFilterActive = filterItem !== null;

  // カレンダー日付の計算（メモ化で再計算を防ぐ）
  const calendarDays = useMemo(() => {
    const monthStart = startOfMonth(currentMonth);
    const monthEnd = endOfMonth(currentMonth);
    // カレンダーグリッドは週の開始（月曜日）から週の終了（日曜日）まで表示
    const calendarStart = startOfWeek(monthStart, { weekStartsOn: 1 }); // 1 = Monday
    const calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 1 });
    return eachDayOfInterval({
      start: calendarStart,
      end: calendarEnd,
    });
  }, [currentMonth]);

  // Outfit records を取得する関数（日付範囲ベースで統一）
  const fetchOutfitRecords = useCallback(
    async (photos: PhotoRecord[], monthStart: Date, monthEnd: Date, clearExisting = false) => {
      try {
        // 日付範囲でoutfit recordsを一括取得（写真ありと写真なし両方）
        const startDateStr = format(monthStart, 'yyyy-MM-dd');
        const endDateStr = format(monthEnd, 'yyyy-MM-dd');

        const outfitRecords = await apiClient.get(
          `/api/v2/outfits/date-range?start_date=${startDateStr}&end_date=${endDateStr}`
        );

        logger.debug('Outfit records from API:', outfitRecords);

        const outfitsByDate: DailyOutfits = {};

        // 日付別にグルーピング
        for (const outfitRecord of outfitRecords) {
          const dateKey = outfitRecord.date;
          const outfitRecordId =
            outfitRecord.outfitRecordId ||
            outfitRecord.outfit_record_id ||
            outfitRecord.id;
          // APIレスポンスのフィールド名を確認（clothingItems がキャメルケース）
          const clothingItems = outfitRecord.clothingItems || outfitRecord.clothing_items || outfitRecord.items || [];
          const rentalItems: ExternalRentalItem[] =
            outfitRecord.externalRentalItems ||
            outfitRecord.external_rental_items ||
            [];
          logger.debug('Processing outfit record:', { dateKey, clothingItems: outfitRecord.clothingItems, selected: clothingItems });

          if (clothingItems && clothingItems.length > 0) {
            if (!outfitsByDate[dateKey]) {
              outfitsByDate[dateKey] = [];
            }

            // clothing_itemsを OutfitItem 型に変換
            const convertedItems = clothingItems.map((clothingItem: ExtendedClothingItem, index: number) => ({
              id: `${outfitRecordId}-${index}`,
              outfitRecordId,
              clothingItemId: clothingItem.id,
              manualAdded: true,
              createdAt: new Date().toISOString(),
              clothingItem: {
                id: clothingItem.id,
                name: clothingItem.name,
                category: clothingItem.category,
                brand: clothingItem.brand,
                imageUrls: clothingItem.imageUrls || clothingItem.image_urls, // 両方のフィールド名に対応（キャメルケースを優先）
              }
            }));

            const convertedRentalItems = rentalItems.map(
              (rentalItem: ExternalRentalItem, index: number) => ({
                id: `${outfitRecordId}-rental-${index}`,
                outfitRecordId,
                clothingItemId: `rental:${rentalItem.id || index}`,
                manualAdded: true,
                createdAt: new Date().toISOString(),
                clothingItem: {
                  id: rentalItem.id,
                  name: rentalItem.name || 'レンタルアイテム',
                  category: 'OTHER',
                  brand: rentalItem.brand || undefined,
                  imageUrls: rentalItem.imageUrl
                    ? {
                        original: rentalItem.imageUrl,
                        thumbnails: {
                          thumb_200: rentalItem.imageUrl,
                          thumb_400: rentalItem.imageUrl,
                        },
                      }
                    : undefined,
                },
              })
            );

            // 同じ日付のrecordが複数ある場合はマージ（最初の4つのみ表示）
            const existingItemIds = outfitsByDate[dateKey].map(
              (item: OutfitItem) => item.clothingItemId
            );
            const newItems = [...convertedItems, ...convertedRentalItems].filter(
              (item: OutfitItem) => !existingItemIds.includes(item.clothingItemId)
            );
            outfitsByDate[dateKey] = [
              ...outfitsByDate[dateKey],
              ...newItems,
            ].slice(0, 4);
          } else if (rentalItems.length > 0) {
            if (!outfitsByDate[dateKey]) {
              outfitsByDate[dateKey] = [];
            }

            const convertedRentalItems = rentalItems.map(
              (rentalItem: ExternalRentalItem, index: number) => ({
                id: `${outfitRecordId}-rental-${index}`,
                outfitRecordId,
                clothingItemId: `rental:${rentalItem.id || index}`,
                manualAdded: true,
                createdAt: new Date().toISOString(),
                clothingItem: {
                  id: rentalItem.id,
                  name: rentalItem.name || 'レンタルアイテム',
                  category: 'OTHER',
                  brand: rentalItem.brand || undefined,
                  imageUrls: rentalItem.imageUrl
                    ? {
                        original: rentalItem.imageUrl,
                        thumbnails: {
                          thumb_200: rentalItem.imageUrl,
                          thumb_400: rentalItem.imageUrl,
                        },
                      }
                    : undefined,
                },
              })
            );

            const existingItemIds = outfitsByDate[dateKey].map(
              (item: OutfitItem) => item.clothingItemId
            );
            const newItems = convertedRentalItems.filter(
              (item: OutfitItem) => !existingItemIds.includes(item.clothingItemId)
            );
            outfitsByDate[dateKey] = [
              ...outfitsByDate[dateKey],
              ...newItems,
            ].slice(0, 4);
          }
        }

        logger.debug('Final outfitsByDate:', outfitsByDate);

        // 既存データの処理：月変更時はクリア、通常更新時はマージ
        if (clearExisting) {
          setDailyOutfits(outfitsByDate);
        } else {
          setDailyOutfits(prevOutfits => ({
            ...prevOutfits,
            ...outfitsByDate
          }));
        }
      } catch (error) {
        logger.error('Failed to fetch outfit records:', error);
        setDailyOutfits({});
      }
    },
    []
  );

  const fetchMonthPhotos = useCallback(async (clearExistingData = false) => {
    setLoading(true);
    try {
      // 現在の月の期間を設定
      const monthStart = startOfMonth(currentMonth);
      const monthEnd = endOfMonth(currentMonth);
      const startDateStr = format(monthStart, 'yyyy-MM-dd');
      const endDateStr = format(monthEnd, 'yyyy-MM-dd');

      const photos = await apiClient.get<PhotoRecord[]>(
        `/api/v2/photos?start_date=${startDateStr}&end_date=${endDateStr}&limit=200`
      );

      // APIで既に月フィルタリング済のため、追加フィルタリング不要

      // 日付別にグループ化（JST基準）
      const groupedPhotos: DailyPhotos = {};
      photos.forEach(photo => {
        try {
          // capturedAtから日付キーを生成（既にJST）
          const capturedAt =
            photo.capturedAt ||
            (photo as unknown as Record<string, unknown>).captured_at;
          const dateKey = dateUtils.extractDateFromISO(capturedAt as string);
          if (!groupedPhotos[dateKey]) {
            groupedPhotos[dateKey] = [];
          }
          groupedPhotos[dateKey].push(photo);
        } catch (error) {
          logger.warn(
            'Invalid date format for photo:',
            photo.id,
            photo.capturedAt,
            error
          );
        }
      });

      setDailyPhotos(groupedPhotos);

      // 写真に対応する outfit records を取得（写真なしも含む）
      await fetchOutfitRecords(photos, monthStart, monthEnd, clearExistingData);
    } catch (error) {
      logger.error('Failed to fetch photos:', error);
      setDailyPhotos({});
    } finally {
      setLoading(false);
    }
  }, [currentMonth, fetchOutfitRecords]); // fetchOutfitRecords を含める

  // 初期読み込みと月変更時のみ実行（既存データをクリア）
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 月変更に応じたカレンダー再取得（fetchMonthPhotos 内部で setState）
    fetchMonthPhotos(true); // 月変更時は既存データをクリア
  }, [currentMonth, fetchMonthPhotos]); // fetchMonthPhotos を含める（useCallbackで安定化済）

  // refreshTrigger 変更時のみ実行（既存データを保持してマージ）
  useEffect(() => {
    if (refreshTrigger && refreshTrigger > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- リフレッシュトリガーによる再取得（fetchMonthPhotos 内部で setState）
      fetchMonthPhotos(false); // 既存データを保持
    }
  }, [refreshTrigger, fetchMonthPhotos]); // fetchMonthPhotos を含める（useCallbackで安定化済）

  // onOutfitSaved変更時に適切な月に移動する処理
  useEffect(() => {
    if (onOutfitSaved) {
      const wrappedOnOutfitSaved = (recordedDate?: string) => {
        if (recordedDate) {
          try {
            const savedDate = parseISO(recordedDate);
            const savedYear = savedDate.getFullYear();
            const savedMonth = savedDate.getMonth();

            const currentYear = currentMonth.getFullYear();
            const currentMonthNum = currentMonth.getMonth();

            // 保存された日付の月と現在表示中の月が異なる場合、月を変更
            if (savedYear !== currentYear || savedMonth !== currentMonthNum) {
              const newMonth = new Date(savedYear, savedMonth, 1);
              setCurrentMonth(newMonth);
              onMonthChange?.(newMonth);
            }
          } catch (error) {
            logger.error('Failed to parse recorded date:', error);
          }
        }

        // 元のonOutfitSavedコールバックも実行
        onOutfitSaved(recordedDate);
      };

      // この関数をグローバルに保存して、他のコンポーネントから呼べるようにする
      (window as Window & { __outfitCalendarSaved?: (recordedDate?: string) => void }).__outfitCalendarSaved = wrappedOnOutfitSaved;
    }
  }, [onOutfitSaved, currentMonth]);

  const handlePrevMonth = () => {
    const newMonth = subMonths(currentMonth, 1);
    setCurrentMonth(newMonth);
    onMonthChange?.(newMonth);
    setSelectedDate(null);
  };

  const handleNextMonth = () => {
    const newMonth = addMonths(currentMonth, 1);
    setCurrentMonth(newMonth);
    onMonthChange?.(newMonth);
    setSelectedDate(null);
  };

  const handleDateClick = (date: Date) => {
    const dateKey = format(date, 'yyyy-MM-dd');
    const photosForDate = dailyPhotos[dateKey] || [];
    const outfitItemsForDate = dailyOutfits[dateKey] || [];

    // 写真が1枚でもある場合、またはワードローブ記録がある場合は、
    // モーダルをスキップして直接コーディネート記録画面に飛ぶ
    if ((photosForDate.length > 0 || outfitItemsForDate.length > 0) && onPhotoSelect) {
      onPhotoSelect(photosForDate, date);
      return;
    }

    // 写真もワードローブ記録もない場合はモーダルを表示
    setSelectedDate(date);
    setShowDateDetail(true);
  };

  const handlePhotoSelect = () => {
    if (selectedDate) {
      const dateKey = format(selectedDate, 'yyyy-MM-dd');
      const photosForDate = dailyPhotos[dateKey] || [];

      if (onPhotoSelect) {
        onPhotoSelect(photosForDate, selectedDate);
      }
      setShowDateDetail(false);
    }
  };

  const handleRegisterFullBody = () => {
    if (onRegisterFullBody && selectedDate) {
      onRegisterFullBody(selectedDate);
    }
    setShowDateDetail(false);
  };

  // スワイプ判定のための定数
  const minSwipeDistance = 50;

  // スワイプハンドラー
  const handleTouchStart = (e: React.TouchEvent) => {
    setTouchEnd(null);
    setTouchStart({
      x: e.targetTouches[0].clientX,
      y: e.targetTouches[0].clientY,
    });
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    setTouchEnd({
      x: e.targetTouches[0].clientX,
      y: e.targetTouches[0].clientY,
    });
  };

  const handleTouchEnd = () => {
    if (!touchStart || !touchEnd) return;

    const distanceX = touchStart.x - touchEnd.x;
    const distanceY = touchStart.y - touchEnd.y;
    const isRightSwipe =
      distanceX < -minSwipeDistance && Math.abs(distanceY) < 100;

    if (isRightSwipe && goBack) {
      goBack(); // 右スワイプで前の画面に戻る
    }
  };

  const getDayPhotoInfo = (date: Date) => {
    const dateKey = format(date, 'yyyy-MM-dd');
    const photos = dailyPhotos[dateKey] || [];
    const outfitItems = dailyOutfits[dateKey] || [];

    // 新しい写真を優先（最新の capturedAt でソート）
    const sortedPhotos = photos.sort((a, b) => {
      const timeA = new Date(
        a.capturedAt ||
          ((a as unknown as Record<string, unknown>).captured_at as string)
      ).getTime();
      const timeB = new Date(
        b.capturedAt ||
          ((b as unknown as Record<string, unknown>).captured_at as string)
      ).getTime();
      return timeB - timeA;
    });
    const latestPhoto = sortedPhotos[0]; // 最新の写真のみ使用

    const result = {
      hasPhotos: photos.length > 0,
      hasConfirmedOutfits: outfitItems.length > 0,
      hasManualOutfits: outfitItems.length > 0 && photos.length === 0, // Manual outfits without photos
      representativePhoto: latestPhoto, // 最新の写真のみ表示
      outfitItems,
      photos, // AI 検出ステータス確認用
    };

    return result;
  };

  return (
    <div
      className="space-y-6"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Calendar Navigation */}
      <div>
        <div className="p-6 bg-white rounded-lg">
          {/* 服フィルター適用中のバナー */}
          {isFilterActive && (
            <div className="mb-4">
              <div className="flex items-center gap-3 p-2 pl-3 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="w-8 h-8 flex-shrink-0 rounded-md overflow-hidden bg-white flex items-center justify-center">
                  {(() => {
                    const url = getBestImageUrl(
                      filterItem?.imageUrls,
                      apiUrl,
                      true
                    );
                    return url ? (
                      <img
                        src={url}
                        alt={filterItem?.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <Shirt className="w-4 h-4 text-amber-500" />
                    );
                  })()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">
                    {filterItem?.name}
                  </p>
                  <p className="text-xs text-gray-500">
                    {filterLoading
                      ? '着用日を読み込み中...'
                      : `着用日 ${filterDates?.size ?? 0} 日`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowItemPicker(true)}
                  className="text-xs text-gray-500 hover:underline px-2 py-1 flex-shrink-0"
                >
                  変更
                </button>
                <button
                  type="button"
                  onClick={clearFilter}
                  aria-label="フィルターを解除"
                  className="hover:bg-amber-100 rounded-full p-1 flex-shrink-0"
                >
                  <X className="w-4 h-4 text-gray-500" />
                </button>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between mb-6">
            <Button
              variant="outline"
              size="sm"
              onClick={handlePrevMonth}
              className="flex items-center gap-2"
            >
              <ChevronLeft className="w-4 h-4" />
              前月
            </Button>

            <h3 className="text-xl font-bold">
              {format(currentMonth, 'yyyy 年 M 月', { locale: ja })}
            </h3>

            <Button
              variant="outline"
              size="sm"
              onClick={handleNextMonth}
              className="flex items-center gap-2"
            >
              次月
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
              <span className="ml-2 text-gray-600">
                カレンダーを読み込み中...
              </span>
            </div>
          ) : (
            <>
              {/* Calendar Grid */}
              <div className="grid grid-cols-7 gap-1 mb-4">
                {/* Week header */}
                {['月', '火', '水', '木', '金', '土', '日'].map(day => (
                  <div
                    key={day}
                    className="text-center text-sm font-medium text-gray-500 py-2"
                  >
                    {day}
                  </div>
                ))}

                {/* Calendar days */}
                {calendarDays.map(date => {
                  const dayInfo = getDayPhotoInfo(date);
                  const isCurrentMonth = isSameMonth(date, currentMonth);
                  const isTodayDate = isToday(date);
                  const isSelected = Boolean(
                    selectedDate && isSameDay(date, selectedDate)
                  );
                  const isFilterMatch = Boolean(
                    isFilterActive &&
                      filterDates?.has(format(date, 'yyyy-MM-dd'))
                  );

                  return (
                    <CalendarDay
                      key={date.toString()}
                      date={date}
                      isCurrentMonth={isCurrentMonth}
                      isToday={isTodayDate}
                      isSelected={isSelected}
                      dayInfo={dayInfo}
                      onClick={() => handleDateClick(date)}
                      apiUrl={apiUrl}
                      isFilterActive={isFilterActive}
                      isFilterMatch={isFilterMatch}
                    />
                  );
                })}
              </div>

              {/* 服で絞り込む入口（使用頻度が低いためカレンダー下中央に配置） */}
              {!isFilterActive && (
                <div className="flex justify-center mt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowItemPicker(true)}
                    className="flex items-center gap-2"
                  >
                    <Shirt className="w-4 h-4" />
                    服で絞り込む
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* 服フィルターのアイテム選択モーダル */}
      <ClothingItemFilterPicker
        open={showItemPicker}
        apiUrl={apiUrl}
        onSelect={handleSelectFilterItem}
        onClose={() => setShowItemPicker(false)}
      />

      {/* Date Detail Modal */}
      <Dialog open={showDateDetail} onOpenChange={setShowDateDetail}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {selectedDate &&
                format(selectedDate, 'yyyy 年 M 月 d 日（E）', { locale: ja })}
            </DialogTitle>
            <DialogDescription>
              選択された日付の写真とコーディネートを表示します
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Date Photos and Outfits Preview */}
            {selectedDate &&
              (() => {
                const dateKey = format(selectedDate, 'yyyy-MM-dd');
                const photos = dailyPhotos[dateKey] || [];
                const outfitItems = dailyOutfits[dateKey] || [];

                return (
                  <div className="space-y-3">
                    {photos.length > 0 || outfitItems.length > 0 ? (
                      <>
                        {/* Outfit Items Grid */}
                        {outfitItems.length > 0 && (
                          <div>
                            <h4 className="text-sm font-medium text-gray-700 mb-2">
                              着用アイテム
                            </h4>
                            <OutfitItemGrid
                              outfitItems={outfitItems}
                              apiUrl={apiUrl}
                            />
                          </div>
                        )}

                        {/* Photo Thumbnails */}
                        {photos.length > 0 && (
                          <div>
                            <div className="flex justify-center">
                              <div className="grid grid-cols-3 gap-2 max-w-48">
                                {photos.slice(0, 6).map(photo => (
                                  <div
                                    key={photo.id}
                                    className="aspect-square relative overflow-hidden rounded border border-gray-200 cursor-pointer hover:ring-2 hover:ring-blue-300 transition-all"
                                    onClick={() => {
                                      // 写真をクリックした場合、詳細画面を開く
                                      if (onPhotoSelect) {
                                        onPhotoSelect(photos, selectedDate!);
                                      }
                                      setShowDateDetail(false);
                                    }}
                                  >
                                    <LazyImage
                                      src={
                                        photo.aiAnnotationImageUrl ||
                                        `${apiUrl}/api/v2/photos/${photo.id}`
                                      }
                                      alt={`${format(parseISO(photo.capturedAt), 'HH:mm')} の写真`}
                                      className="w-full h-full object-cover"
                                      placeholderSrc="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100'%3E%3Crect width='100' height='100' fill='%23e5e7eb'/%3E%3C/svg%3E"
                                      onError={() => {
                                        // AI annotation image が失敗した場合は通常の写真にフォールバック
                                        // LazyImage コンポーネントが自動的にエラー処理
                                      }}
                                    />
                                    <div className="absolute bottom-0 left-0 right-0 bg-black/50 text-white text-xs px-1 py-0.5">
                                      {format(
                                        parseISO(photo.capturedAt),
                                        'HH:mm'
                                      )}
                                    </div>
                                  </div>
                                ))}
                                {photos.length > 6 && (
                                  <div
                                    className="aspect-square border border-gray-200 rounded flex items-center justify-center bg-gray-100 text-gray-500 text-xs cursor-pointer hover:bg-gray-200 transition-colors"
                                    onClick={() => {
                                      // 残りの写真も表示するため詳細画面を開く
                                      if (onPhotoSelect) {
                                        onPhotoSelect(photos, selectedDate!);
                                      }
                                      setShowDateDetail(false);
                                    }}
                                  >
                                    +{photos.length - 6}枚
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-center py-6 text-gray-500">
                        この日の記録はありません
                      </div>
                    )}
                  </div>
                );
              })()}

            {/* Action Buttons */}
            <div className="flex flex-col gap-2 pt-4">
              <Button
                onClick={handlePhotoSelect}
                className="w-full transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                variant="default"
              >
                📸 コーディネートを記録
              </Button>

              {onRegisterFullBody && (
                <Button
                  onClick={handleRegisterFullBody}
                  className="w-full transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                  variant="outline"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  全身を登録
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

interface CalendarDayProps {
  date: Date;
  isCurrentMonth: boolean;
  isToday: boolean;
  isSelected: boolean;
  dayInfo: {
    hasPhotos: boolean;
    hasConfirmedOutfits: boolean;
    hasManualOutfits: boolean;
    representativePhoto?: PhotoRecord;
    outfitItems: OutfitItem[];
    photos: PhotoRecord[];
  };
  onClick: () => void;
  apiUrl: string;
  isFilterActive: boolean;
  isFilterMatch: boolean;
}

const CalendarDay: React.FC<CalendarDayProps> = ({
  date,
  isCurrentMonth,
  isToday,
  isSelected,
  dayInfo,
  onClick,
  apiUrl,
  isFilterActive,
  isFilterMatch,
}) => {
  // フィルター中: 該当日は強調、非該当日は淡色にして着用日を目立たせる
  const isDimmed = isFilterActive && !isFilterMatch;
  return (
    <div
      className={`
        aspect-square cursor-pointer transition-all duration-200 overflow-hidden
        border border-gray-200 rounded
        ${isCurrentMonth ? 'text-gray-900' : 'text-gray-400'}
        ${isToday ? 'ring-2 ring-blue-500' : ''}
        ${isSelected ? 'ring-2 ring-purple-500 bg-purple-50' : ''}
        ${isFilterMatch ? 'ring-2 ring-amber-500 bg-amber-50' : ''}
        ${isDimmed ? 'opacity-30 grayscale' : ''}
        ${dayInfo.hasPhotos ? 'hover:shadow-md' : 'hover:bg-gray-50'}
      `}
      onClick={onClick}
    >
      <div className="h-full flex flex-col overflow-hidden">
        {/* Date number */}
        <div className="text-xs font-medium p-1 text-center flex-shrink-0">
          {format(date, 'd')}
        </div>

        {/* Photo preview, outfit grid, or camera icon */}
        <div className="flex-1 relative overflow-hidden">
          {dayInfo.hasConfirmedOutfits && dayInfo.outfitItems.length > 0 ? (
            <div className="w-full h-full p-0.5 relative flex items-center justify-center">
              <div className="w-full max-h-full">
                <OutfitItemGrid
                  outfitItems={dayInfo.outfitItems}
                  apiUrl={apiUrl}
                  size="small"
                />
              </div>
              {/* ワードローブが選択されている場合でも写真がある場合は中央にカメラアイコンを表示 */}
              {dayInfo.hasPhotos && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div
                    className={`w-8 h-8 ${getCameraIconColor(dayInfo.photos, dayInfo.outfitItems || [])} rounded-full flex items-center justify-center shadow-lg`}
                  >
                    <Camera className="w-4 h-4 text-white" />
                  </div>
                </div>
              )}
            </div>
          ) : dayInfo.hasPhotos ? (
            <div className="h-full flex items-center justify-center bg-gray-100">
              {/* 丸で囲ったカメラアイコン（AI検出ステータス対応） */}
              <div
                className={`w-8 h-8 ${getCameraIconColor(dayInfo.photos, dayInfo.outfitItems || [])} rounded-full flex items-center justify-center`}
              >
                <Camera className="w-4 h-4 text-white" />
              </div>
            </div>
          ) : (
            <div className="h-full bg-gray-50" />
          )}
        </div>
      </div>
    </div>
  );
};
