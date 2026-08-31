import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  ArrowLeft,
  Loader2,
  Eye,
  Shirt,
  CheckCircle2,
  XCircle,
  Clock,
  Trash2,
  Wallet,
} from 'lucide-react';
import { CategoryClothingSelector } from './CategoryClothingSelector';
import { API_URL } from '@/config/urls';
import { transformForApiRequest } from '@/utils/apiResponseTransformer';
import { apiClient } from '@/services/apiClient';
import type {
  Photo,
  CreateOutfitRecordRequest,
} from '@/types/outfit';
import type { ExternalRentalItem } from '@/types/externalRentals';
import { useExternalRentalData } from '@/hooks/useExternalRentalData';
import { logger } from '@/utils/logger';
import { formatNumber, formatPercent } from '@/utils/numberUtils';
import { isValidHttpUrl } from '@/utils/urlValidation';
import { cn } from '@/lib/utils';
import { getCandidateId, getCandidateScore, rankCandidates } from './candidateScoring';
import { useItemDetails } from './hooks/useItemDetails';
import { useAIDetection } from './hooks/useAIDetection';
import { useExistingOutfitRecord } from './hooks/useExistingOutfitRecord';

const getRentalImageUrl = (item?: ExternalRentalItem): string => {
  if (item?.imageUrl && isValidHttpUrl(item.imageUrl)) {
    return item.imageUrl;
  }
  return '/placeholder-clothing.png';
};

interface PhotoClothingSelectionProps {
  photo: Photo;
  onBack: () => void;
  onSaveComplete: (message: string, recordedDate?: string) => void;
}

export function EnhancedPhotoClothingSelection({
  photo,
  onBack,
  onSaveComplete,
}: PhotoClothingSelectionProps) {
  const [selectedItems, setSelectedItems] = useState<string[]>([]);
  const [selectedRentalItems, setSelectedRentalItems] = useState<string[]>([]);
  const [selectedRentalDetails, setSelectedRentalDetails] = useState<
    Record<string, ExternalRentalItem>
  >({});
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'photo' | 'cropped' | 'category'>(
    'photo'
  );
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);  // GCS URL の状態を追加
  const [isLoadingPhoto, setIsLoadingPhoto] = useState(true);  // 写真読み込み中フラグ
  // 写真の撮影時刻を取得（完全な datetime として使用）
  const recordedDateTime = photo.createdAt ? new Date(photo.createdAt).toISOString() : new Date().toISOString();
  // 日付部分のみ（既存のロジックで使用）
  const selectedDate = recordedDateTime.split('T')[0];

  const {
    summary: rentalSummary,
    loading: rentalLoading,
    error: rentalError,
    reload: reloadRentalSummary,
  } = useExternalRentalData();

  const availableRentalItems = useMemo(() => {
    if (!rentalSummary) {
      return [];
    }
    const candidates = [
      ...(rentalSummary.items ?? []),
      ...(rentalSummary.returnedItems ?? []),
    ];
    return candidates.filter(item => {
      if (item.status === 'ACTIVE') {
        return true;
      }
      const dueDate = item.returnDueDate?.split('T')[0];
      const returnedAt = item.returnedAt?.split('T')[0];
      const lastWornAt = item.lastWornAt?.split('T')[0];
      const cutoffDate = dueDate || returnedAt || lastWornAt;
      if (!cutoffDate) {
        return false;
      }
      return selectedDate <= cutoffDate;
    });
  }, [rentalSummary, selectedDate]);

  const {
    selectedItemsDetails,
    wardrobeCostError,
    wardrobeCostSummary,
    displayedWardrobeTotal,
  } = useItemDetails(selectedItems);

  const {
    aiDetectionDetails,
    isLoadingAIDetails,
    isReprocessingAIDetection,
    fetchAIDetectionDetails,
    handleAIDetectionReprocess,
  } = useAIDetection({
    photo,
    photoUrl,
    setPhotoUrl,
    setIsLoadingPhoto,
    setError,
  });

  const { fetchExistingOutfitRecord } = useExistingOutfitRecord({
    photo,
    selectedDate,
    setSelectedItems,
    setSelectedRentalItems,
    setSelectedRentalDetails,
  });

  useEffect(() => {
    if (!rentalSummary) {
      return;
    }

    // eslint-disable-next-line react-hooks/set-state-in-effect -- rentalSummary 変化に追従した詳細マップ更新
    setSelectedRentalDetails(prev => {
      const updated = { ...prev };
      for (const item of rentalSummary.items) {
        updated[item.id] = item;
      }
      for (const item of rentalSummary.returnedItems ?? []) {
        updated[item.id] = item;
      }
      return updated;
    });
  }, [rentalSummary]);

  const handleRentalToggle = useCallback(
    (rentalId: string, rentalItem?: ExternalRentalItem) => {
      setSelectedRentalItems(prev => {
        if (prev.includes(rentalId)) {
          return prev.filter(id => id !== rentalId);
        }
        return [...prev, rentalId];
      });

      if (rentalItem) {
        setSelectedRentalDetails(prev => ({
          ...prev,
          [rentalId]: rentalItem,
        }));
      }
    },
    [],
  );

  const inactiveSelectedRentalItems = useMemo(() => {
    if (availableRentalItems.length === 0) {
      return selectedRentalItems;
    }
    const activeIds = new Set(availableRentalItems.map(item => item.id));
    return selectedRentalItems.filter(id => !activeIds.has(id));
  }, [availableRentalItems, selectedRentalItems]);

  const shouldRenderRentalSection =
    rentalLoading ||
    Boolean(rentalError) ||
    availableRentalItems.length > 0 ||
    inactiveSelectedRentalItems.length > 0;

  const handleRentalImageError = useCallback(
    (event: React.SyntheticEvent<HTMLImageElement>) => {
      event.currentTarget.src = '/placeholder-clothing.png';
    },
    [],
  );

  const handlePhotoLoad = useCallback(
    () => {
      setIsLoadingPhoto(false);
    },
    [],
  );

  useEffect(() => {
    // photo が変更されたときエラーをクリア
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 写真切替時のエラー・読込状態の同期更新
    setError(null);

    // 写真IDがある場合、または写真なしでも日付が指定されている場合は既存レコードを取得
    if ((photo.id && photo.id.trim() !== '') || (!photo.id && selectedDate)) {
      void fetchExistingOutfitRecord();
    }

    // props から photoUrl が渡されている場合は即座に使用
    if (isValidHttpUrl(photo.photoUrl)) {
      setPhotoUrl(photo.photoUrl);
      setIsLoadingPhoto(false);
    }
    if (photo.id && photo.id.trim() !== '') {
      fetchAIDetectionDetails();
    } else if (!photo.photoUrl) {
      setIsLoadingPhoto(false);
    }
  }, [photo.id, photo.photoUrl, selectedDate, fetchExistingOutfitRecord, fetchAIDetectionDetails]);


  const handleSave = async () => {
    if (selectedItems.length === 0) {
      setError('少なくとも一つの服を選択してください');
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      // 1. outfit record を保存
      const uniqueRentalIds = Array.from(new Set(selectedRentalItems));

      const outfitData: CreateOutfitRecordRequest = {
        photoId: photo.id,
        clothingItemIds: selectedItems,
        externalRentalItemIds: uniqueRentalIds,
        notes: `Enhanced selection: ${selectedItems.length} items`,
        recordedAt: recordedDateTime, // 写真の完全な撮影時刻を使用
      };

      const transformedData = transformForApiRequest(outfitData);

      logger.dev('[EnhancedPhotoClothingSelection] Sending data to API:', {
        original: outfitData,
        transformed: transformedData,
        selectedDate: selectedDate
      });

      await apiClient.post('/api/v2/outfits/record', outfitData);
      await reloadRentalSummary();

      // 2. 保存成功をすぐに通知
      const successMessage = 'コーディネートを記録しました';
      onSaveComplete(successMessage, selectedDate);

    } catch (error) {
      logger.error('保存エラー:', error);
      setError('保存に失敗しました。もう一度お試しください。');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    setError(null);

    try {
      try {
        const result = await apiClient.delete(`/api/v2/outfits/photo/${photo.id}`);
        interface DeleteResult {
          message?: string;
        }
        const message = (result as DeleteResult).message || 'コーディネートを削除しました';
        onSaveComplete(message);
      } catch (deleteError) {
        const apiError = deleteError as { status?: number; message?: string };
        if (apiError.status === 404) {
          // 404 error - photo or record not found, but treat as successful deletion
          logger.warn(
            'Photo or outfit record not found, treating as successful deletion'
          );
          onSaveComplete('写真を削除しました');
          onBack();
          return;
        } else {
          throw deleteError;
        }
      }
      onBack();
    } catch (error) {
      logger.error('削除エラー:', error);
      const errorMessage =
        error instanceof Error
          ? error.message
          : '削除に失敗しました。もう一度お試しください。';
      setError(errorMessage);
    } finally {
      setIsDeleting(false);
      setShowDeleteDialog(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="sm" onClick={onBack}>
                <ArrowLeft className="w-4 h-4 mr-2" />
                戻る
              </Button>
              <div>
                <h1 className="text-xl font-bold">ワードローブ選択</h1>
                <p className="text-sm text-gray-600">
                  {new Date(photo.createdAt)
                    .toLocaleDateString('ja-JP', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                      weekday: 'short',
                    })
                    .replace(/\(/g, '（')
                    .replace(/\)/g, '）')
                    .replace(
                      /(\d{4})年(\d{1,2})月(\d{1,2})日/,
                      '$1 年 $2 月 $3 日'
                    )}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={() => setShowDeleteDialog(true)}
                disabled={isDeleting}
                variant="ghost"
                size="sm"
                className="text-gray-400 hover:text-red-600 hover:bg-red-50"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-4">
        <div className="space-y-6">
          {/* Photo and AI Results - 写真がある場合のみ表示 */}
          {photo.id && photo.id.trim() !== '' && (
            <div className="space-y-4">
              {/* View Mode Toggle */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold flex items-center gap-2">
                    <Eye className="w-5 h-5" />
                    全身
                  </h2>
                  <div className="flex flex-wrap gap-1">
                    <Button
                      variant={viewMode === 'photo' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setViewMode('photo')}
                    >
                      原画像
                    </Button>
                    <Button
                      variant={viewMode === 'cropped' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setViewMode('cropped')}
                      disabled={
                        !aiDetectionDetails ||
                        aiDetectionDetails.status === 'pending' ||
                        aiDetectionDetails.status === 'processing'
                      }
                      className="flex items-center gap-1"
                    >
                      {aiDetectionDetails?.status === 'completed' ? (
                        <CheckCircle2 className="w-3 h-3" />
                      ) : aiDetectionDetails?.status === 'pending' ? (
                        <Clock className="w-3 h-3" />
                      ) : aiDetectionDetails?.status === 'failed' ? (
                        <XCircle className="w-3 h-3" />
                      ) : null}
                      ワードローブ検出
                    </Button>
                  </div>
                </div>
                <div className="flex justify-center">
                  <div
                    className="w-64 h-80 bg-gray-100 rounded-lg overflow-hidden flex items-center justify-center relative"
                  >
                    {isLoadingPhoto && viewMode !== 'cropped' ? (
                      <div className="flex flex-col items-center gap-2">
                        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
                        <p className="text-sm text-gray-500">写真を読み込み中...</p>
                      </div>
                    ) : viewMode === 'cropped' && aiDetectionDetails?.croppedImages && aiDetectionDetails.croppedImages.length > 0 ? (
                      <div className="w-full h-full p-4 overflow-y-auto">
                        <div className="space-y-4">
                          {aiDetectionDetails.detectedItems?.map((item, index) => (
                              <div key={index} className="text-center">
                                <p className="text-sm font-medium mb-2">
                                  {item.category} (信頼度: {(item.confidence || 0).toFixed(2)})
                                </p>
                                {item.croppedImageUrl ? (
                                  <img
                                    src={item.croppedImageUrl}
                                    alt={`${item.category} 切り抜き`}
                                    className="max-w-full max-h-48 mx-auto object-contain bg-white border rounded"
                                  />
                                ) : (
                                  <p className="text-xs text-gray-500">画像URLが見つかりません</p>
                                )}
                              </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                        <img
                          src={photoUrl || `${API_URL}/v2/photos/${photo.id}`}
                          alt="選択した写真"
                          className="w-full h-full object-cover"
                          onLoad={handlePhotoLoad}
                          onError={() => {
                            setIsLoadingPhoto(false);
                          }}
                        />
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

        {/* Selection Sections */}
        <div
          className={`space-y-8 ${photo.id && photo.id.trim() !== '' ? 'mt-12' : 'mt-6'}`}
        >
          {shouldRenderRentalSection && (
            <section>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <Clock className="w-5 h-5" />
                  レンタル
                </h2>
              </div>

              {rentalLoading ? (
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  レンタル情報を読み込み中です…
                </div>
              ) : rentalError ? (
                <Alert className="border-amber-200 bg-amber-50">
                  <AlertDescription className="flex items-center justify-between gap-3 text-amber-800">
                    <span>{rentalError}</span>
                    <Button size="sm" variant="outline" onClick={() => reloadRentalSummary()}>
                      再読み込み
                    </Button>
                  </AlertDescription>
                </Alert>
              ) : availableRentalItems.length > 0 ? (
                <div className="flex flex-wrap gap-3">
                  {availableRentalItems.map(item => {
                    const isSelected = selectedRentalItems.includes(item.id);
                    const imageSrc = getRentalImageUrl(item);

                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => handleRentalToggle(item.id, item)}
                        title={item.name}
                        className={cn(
                          'relative flex h-20 w-20 items-center justify-center overflow-hidden rounded-lg border-2 bg-white transition-all focus:outline-none focus:ring-2 focus:ring-blue-400',
                          isSelected
                            ? 'border-blue-500 ring-2 ring-blue-200'
                            : 'border-gray-200 hover:border-gray-300',
                        )}
                      >
                        {imageSrc === '/placeholder-clothing.png' ? (
                          <div className="flex h-full w-full items-center justify-center bg-gray-100">
                            <Shirt className="h-8 w-8 text-gray-400" />
                          </div>
                        ) : (
                          <img
                            src={imageSrc}
                            alt={`${item.name} の画像`}
                            className="h-full w-full object-cover"
                            loading="lazy"
                            onError={handleRentalImageError}
                          />
                        )}
                      </button>
                    );
                  })}
                </div>
              ) : null}

              {inactiveSelectedRentalItems.length > 0 && (
                <div className="mt-6 space-y-2">
                  <p className="text-xs font-medium text-gray-500">
                    非アクティブ（返却済など）のレンタル
                  </p>
                  {inactiveSelectedRentalItems.map(rentalId => {
                    const rentalDetail = selectedRentalDetails[rentalId];
                    return (
                      <div
                        key={rentalId}
                        className="flex items-center justify-between gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-600"
                      >
                        <div>
                          <p className="font-medium text-gray-700">
                            {rentalDetail?.name ?? 'レンタルアイテム'}
                          </p>
                          {rentalDetail?.brand && (
                            <p className="text-xs text-gray-500">{rentalDetail.brand}</p>
                          )}
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleRentalToggle(rentalId, rentalDetail)}
                        >
                          選択解除
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          <section className="border-t border-gray-200 pt-6">
            <div className="flex items-center justify-between mb-4">
              <h2
                className="text-lg font-semibold flex items-center gap-2"
                role="heading"
                aria-level={2}
              >
                <Shirt className="w-5 h-5" aria-hidden="true" />
                ワードローブ
              </h2>
            </div>
            <CategoryClothingSelector
              selectedItems={selectedItems}
              onItemsChange={setSelectedItems}
              showSelectedCount={true}
              photoId={photo.id}
              selectedDate={selectedDate || null}
            />
            <div className="mt-6 mb-4 space-y-4 pb-4">
              <div className="flex items-center justify-between">
                <h2
                  className="text-lg font-semibold flex items-center gap-2"
                  role="heading"
                  aria-level={2}
                >
                  <Wallet className="w-5 h-5" aria-hidden="true" />
                  コスト
                </h2>
              </div>
              <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">この日の合計額</p>
                    {wardrobeCostSummary.calculableCount > 0 ? (
                      <div className="mt-1 flex items-baseline gap-2">
                        <span className="text-base font-semibold text-gray-500 leading-none">¥</span>
                        <span className="text-3xl font-semibold text-gray-900 leading-none">
                          {formatNumber(displayedWardrobeTotal)}
                        </span>
                        <span className="text-sm text-gray-500">/ 回</span>
                      </div>
                    ) : (
                      <p className="text-base font-medium text-gray-500">
                        {selectedItems.length === 0 ? 'アイテム未選択' : 'コスト情報なし'}
                      </p>
                    )}
                  </div>
                  <div className="text-xs text-gray-600 space-y-1 text-right">
                    <p>選択 {selectedItems.length} 点</p>
                    {wardrobeCostSummary.calculableCount > 0 && (
                      <p>計算対象 {wardrobeCostSummary.calculableCount} 点</p>
                    )}
                    {wardrobeCostSummary.loadingCount > 0 && (
                      <p className="text-amber-600">情報取得中 {wardrobeCostSummary.loadingCount} 点</p>
                    )}
                    {wardrobeCostSummary.missingCostCount > 0 && (
                      <p>コスト未登録 {wardrobeCostSummary.missingCostCount} 点</p>
                    )}
                  </div>
                </div>
              </div>
              {wardrobeCostError && (
                <Alert className="border-amber-200 bg-amber-50 text-amber-900">
                  <AlertDescription>{wardrobeCostError}</AlertDescription>
                </Alert>
              )}
            </div>
          </section>
        </div>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert className="mt-4 border-red-200 bg-red-50">
            <AlertDescription className="text-red-800">
              {error}
            </AlertDescription>
          </Alert>
        )}

        <section className="mt-8 border-t border-gray-200 pt-6">
          <div className="flex items-center justify-between mb-4">
            <h2
              className="text-lg font-semibold flex items-center gap-2"
              role="heading"
              aria-level={2}
            >
              <Eye className="w-5 h-5" aria-hidden="true" />
              AI 解析データ
            </h2>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => fetchAIDetectionDetails()}
                disabled={isLoadingAIDetails || !photo.id}
              >
                {isLoadingAIDetails ? '再取得中...' : '再取得'}
              </Button>
              <Button
                size="sm"
                variant="default"
                onClick={handleAIDetectionReprocess}
                disabled={isReprocessingAIDetection || !photo.id}
              >
                {isReprocessingAIDetection ? '再解析中...' : '再解析'}
              </Button>
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm space-y-4">
            {aiDetectionDetails ? (
              <>
                <div className="grid gap-2 text-sm text-gray-700 sm:grid-cols-2">
                  <div>
                    <p className="text-xs text-gray-500">ステータス</p>
                    <p className="font-medium">{aiDetectionDetails.status}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">検出アイテム</p>
                    <p className="font-medium">
                      {aiDetectionDetails.detectionCount ??
                        aiDetectionDetails.detectedItems?.length ??
                        0}
                      件
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">処理時間</p>
                    <p className="font-medium">
                      {typeof aiDetectionDetails.processingTimeMs === 'number'
                        ? `${Math.round(aiDetectionDetails.processingTimeMs)} ms`
                        : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">モデル</p>
                    <p className="font-medium">
                      {aiDetectionDetails.modelVersion || 'N/A'}
                    </p>
                  </div>
                </div>
                {aiDetectionDetails.errorMessage && (
                  <Alert className="border-amber-200 bg-amber-50 text-amber-900">
                    <AlertDescription>{aiDetectionDetails.errorMessage}</AlertDescription>
                  </Alert>
                )}
                {aiDetectionDetails.detectedItems &&
                aiDetectionDetails.detectedItems.length > 0 ? (
                  <div className="space-y-4">
                    {aiDetectionDetails.detectedItems.map((item, index) => {
                      const candidates = item.wardrobeMatchCandidates || [];
                      return (
                        <div
                          key={`${item.category || 'item'}-${index}`}
                          className="rounded-xl border border-gray-200 bg-gray-50 p-3"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <p className="text-sm font-semibold text-gray-900">
                                {item.category || 'UNKNOWN'}
                              </p>
                              <p className="text-xs text-gray-600">
                                信頼度 {formatPercent(item.confidence)}
                              </p>
                            </div>
                            {item.bbox && (
                              <div className="text-xs text-gray-600">
                                bbox ({Math.round(item.bbox.x)},{' '}
                                {Math.round(item.bbox.y)}) / {Math.round(item.bbox.width)}
                                ×{Math.round(item.bbox.height)}
                              </div>
                            )}
                          </div>
                          <div className="mt-3 space-y-2 text-xs text-gray-700">
                            <p className="text-gray-500">
                              ワードローブ候補 {candidates.length} 件
                            </p>
                            {candidates.length > 0 ? (
                              <div className="space-y-2">
                                {rankCandidates(candidates).map((candidate, candidateIndex) => (
                                  <div
                                    key={`${getCandidateId(candidate)}-${candidateIndex}`}
                                    className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white bg-white px-3 py-2"
                                  >
                                    <div>
                                      <p className="text-sm font-medium text-gray-800">
                                        {candidate.name || getCandidateId(candidate) || '候補'}
                                      </p>
                                      {(candidate.brand || candidate.subcategory) && (
                                        <p className="text-xs text-gray-500">
                                          {[candidate.brand, candidate.subcategory]
                                            .filter(Boolean)
                                            .join(' / ')}
                                        </p>
                                      )}
                                    </div>
                                    <div className="text-right">
                                      <p className="text-sm font-semibold text-gray-900">
                                        {formatPercent(getCandidateScore(candidate))}
                                      </p>
                                      {candidate.matchReason && (
                                        <p className="text-xs text-gray-500">
                                          {candidate.matchReason}
                                        </p>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-gray-500">候補なし</p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-gray-600">
                    検出データがまだありません。AI 検出が完了すると表示されます。
                  </p>
                )}
                {aiDetectionDetails.rawResults && (
                  <details className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700">
                    <summary className="cursor-pointer font-medium text-gray-800">
                      RAW JSON
                    </summary>
                    <pre className="mt-2 overflow-x-auto whitespace-pre-wrap">
                      {JSON.stringify(aiDetectionDetails.rawResults, null, 2)}
                    </pre>
                  </details>
                )}
              </>
            ) : (
              <p className="text-sm text-gray-600">
                AI 解析データがまだありません。検出が完了すると表示されます。
              </p>
            )}
          </div>
        </section>


      </div>

      {/* Fixed Save Button Footer */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-50">
        <div className="max-w-7xl mx-auto p-4">
          {selectedRentalItems.length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-medium text-gray-700 mb-3">
                レンタル選択済（{selectedRentalItems.length}）
              </h3>
              <div className="flex flex-wrap gap-3">
                {selectedRentalItems.map(rentalId => {
                  const rentalDetail = selectedRentalDetails[rentalId];
                  const imageUrl = getRentalImageUrl(rentalDetail);

                  return (
                    <div key={rentalId} className="relative">
                      <div className="relative">
                        {imageUrl === '/placeholder-clothing.png' ? (
                          <div className="w-16 h-16 bg-gray-100 rounded-lg flex items-center justify-center">
                            <Shirt className="w-8 h-8 text-gray-400" />
                          </div>
                        ) : (
                          <img
                            src={imageUrl}
                            alt={rentalDetail?.name ?? 'レンタルアイテム'}
                            className="w-16 h-16 object-cover rounded-lg"
                            onError={handleRentalImageError}
                          />
                        )}
                        <button
                          onClick={() => handleRentalToggle(rentalId, rentalDetail)}
                          className="absolute -top-2 -right-1 w-5 h-5 bg-blue-500 text-white rounded-full flex items-center justify-center text-xs hover:bg-blue-600 leading-none"
                          style={{ transform: 'translateY(-1px)' }}
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Selected Items Summary */}
          {selectedItems.length > 0 && (
            <div className="mb-4">
              <h3 className="text-sm font-medium text-gray-700 mb-4">
                ワードローブ選択済（{selectedItems.length}）
              </h3>
              <div className="flex flex-wrap gap-3">
                {selectedItems.map(itemId => {
                  const itemDetails = selectedItemsDetails[itemId];

                  const imageSources = itemDetails?.imageUrls ?? itemDetails?.image_urls;

                  let imageUrl = '/placeholder-clothing.png';
                  if (imageSources?.thumbnails?.thumb_200) {
                    imageUrl = imageSources.thumbnails.thumb_200;
                  } else if (imageSources?.thumbnails?.thumb_400) {
                    imageUrl = imageSources.thumbnails.thumb_400;
                  } else if (imageSources?.original) {
                    imageUrl = imageSources.original;
                  }

                  return (
                    <div key={itemId} className="relative">
                      <div className="relative">
                        {imageUrl === '/placeholder-clothing.png' ? (
                          <div className="w-16 h-16 bg-gray-100 rounded-lg flex items-center justify-center">
                            <Shirt className="w-8 h-8 text-gray-400" />
                          </div>
                        ) : (
                          <img
                            src={imageUrl}
                            alt={itemDetails?.name || '服'}
                            className="w-16 h-16 object-cover rounded-lg"
                            onError={(e) => {
                              const target = e.currentTarget as HTMLImageElement;
                              target.style.display = 'none';
                              target.parentElement?.insertAdjacentHTML(
                                'afterbegin',
                                '<div class="w-16 h-16 bg-gray-100 rounded-lg flex items-center justify-center"><svg class="w-8 h-8 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.38 8.57l-1.23 1.85a8 8 0 0 1-7.22 4.44 8 8 0 0 1-7.22-4.44L3.48 8.57a2 2 0 0 1 .43-2.75l2.83-2.12a2 2 0 0 1 2.44.11l2.32 2.32 2.32-2.32a2 2 0 0 1 2.44-.11l2.83 2.12a2 2 0 0 1 .43 2.75zM7 17h10"></path></svg></div>'
                              );
                            }}
                          />
                        )}
                        <button
                          onClick={() =>
                            setSelectedItems(prev =>
                              prev.filter(id => id !== itemId)
                            )
                          }
                          className="absolute -top-2 -right-1 w-5 h-5 bg-red-500 text-white rounded-full flex items-center justify-center text-xs hover:bg-red-600 leading-none"
                          style={{ transform: 'translateY(-1px)' }}
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Save Button */}
          <Button
            onClick={handleSave}
            disabled={isSaving || selectedItems.length === 0}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white py-3 text-lg font-medium rounded-none"
            size="lg"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                保存中...
              </>
            ) : (
              '保存'
            )}
          </Button>
        </div>
      </div>

      {/* Bottom Padding to prevent content from being hidden behind fixed footer */}
      <div className="h-72"></div>

      {showDeleteDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-sm w-full mx-4">
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                記録を削除しますか？
              </h3>
              <p className="text-sm text-gray-600">
                本当に全身写真や日々の記録を削除しますか？ワードローブ自体は消えません
              </p>
            </div>
            <div className="flex gap-3">
              <Button
                onClick={() => setShowDeleteDialog(false)}
                variant="outline"
                className="flex-1"
              >
                キャンセル
              </Button>
              <Button
                onClick={handleDelete}
                disabled={isDeleting}
                variant="destructive"
                className="flex-1"
              >
                {isDeleting ? <>削除中...</> : '削除'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
