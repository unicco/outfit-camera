import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  X,
  ChevronLeft,
  ChevronRight,
  Camera,
  Shirt,
  Clock,
} from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';
import { apiClient } from '@/services/apiClient';
import { OutfitRecord } from '@/types/outfit';
import { logger } from '@/utils/logger';

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
  photoUrl?: string; // GCS URL など外部アクセス可能な URL
}

interface ClothingItem {
  id: string;
  name: string;
  category: string;
  colorPrimary: string;
  imageUrls?: string[];
}

interface DailyPhotoDetailProps {
  photos: PhotoRecord[];
  selectedDate: Date;
  apiUrl: string;
  onClose: () => void;
  onStartClothingSelection?: (photo: PhotoRecord) => void;
}

export const DailyPhotoDetail: React.FC<DailyPhotoDetailProps> = ({
  photos,
  selectedDate,
  apiUrl,
  onClose,
  onStartClothingSelection,
}) => {
  const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);
  const [outfitItems, setOutfitItems] = useState<ClothingItem[]>([]);
  const [loadingOutfit, setLoadingOutfit] = useState(false);

  const currentPhoto = photos[currentPhotoIndex];

  // モーダル表示時に背景スクロールを防ぐ
  useEffect(() => {
    // モーダル表示時に body のスクロールを無効化
    document.body.style.overflow = 'hidden';

    // Escキーでモーダルを閉じる
    const handleEscKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscKey);

    return () => {
      // コンポーネントがアンマウントされる時にスクロールを復元
      document.body.style.overflow = '';
      document.removeEventListener('keydown', handleEscKey);
    };
  }, [onClose]);

  const fetchOutfitForPhoto = useCallback(
    async (photoId: string) => {
      setLoadingOutfit(true);
      try {
        const outfitRecord = await apiClient.get<OutfitRecord>(`/api/v2/outfits/photo/${photoId}`);
        if (outfitRecord && outfitRecord.outfitItems) {
          const items = outfitRecord.outfitItems
            .filter(item => item.clothingItem)
            .map(item => item.clothingItem as ClothingItem);
          setOutfitItems(items);
        } else {
          setOutfitItems([]);
        }
      } catch (error) {
        if (error instanceof Error && 'status' in error && (error as { status: number }).status === 404) {
          // outfit が存在しない場合
          setOutfitItems([]);
        } else {
          logger.error('Failed to fetch outfit:', error);
          setOutfitItems([]);
        }
      } finally {
        setLoadingOutfit(false);
      }
    },
    []
  );

  useEffect(() => {
    if (currentPhoto) {
      // AI検出完了か、手動選択された outfit がある可能性があるので常に取得を試行
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 写真切替時の outfit 再取得（fetchOutfitForPhoto 内部で setState）
      fetchOutfitForPhoto(currentPhoto.id);
    } else {
      setOutfitItems([]);
    }
  }, [currentPhoto, fetchOutfitForPhoto]);

  const handlePrevPhoto = () => {
    setCurrentPhotoIndex(Math.max(0, currentPhotoIndex - 1));
  };

  const handleNextPhoto = () => {
    setCurrentPhotoIndex(Math.min(photos.length - 1, currentPhotoIndex + 1));
  };

  const getPhotoUrl = (photo: PhotoRecord) => {
    // photoUrl が存在する場合はそれを使用（GCS URL など）
    if ('photoUrl' in photo && photo.photoUrl) {
      return photo.photoUrl as string;
    }
    // フォールバック: API 経由での取得（ローカル環境用）
    return `${apiUrl}/api/v2/photos/${photo.id}`;
  };

  const getDisplayImage = (photo: PhotoRecord) => {
    // AI検出結果が確定している場合はカラー、そうでなければ白黒
    const isConfirmed =
      photo.aiDetectionStatus === 'completed' && outfitItems.length > 0;
    return {
      url: getPhotoUrl(photo),
      isGrayscale: !isConfirmed,
    };
  };

  const formatTime = (dateString: string) => {
    try {
      return format(parseISO(dateString), 'HH:mm', { locale: ja });
    } catch {
      return '';
    }
  };

  const getStatusBadge = (photo: PhotoRecord) => {
    if (photo.aiDetectionStatus === 'completed' && outfitItems.length > 0) {
      return {
        text: '確定済',
        variant: 'default' as const,
        color: 'bg-blue-500',
      };
    } else if (photo.aiDetectionStatus === 'completed') {
      return {
        text: '検出完了',
        variant: 'secondary' as const,
        color: 'bg-green-500',
      };
    } else if (photo.aiDetectionStatus === 'pending') {
      return {
        text: '処理中',
        variant: 'outline' as const,
        color: 'bg-yellow-500',
      };
    } else {
      return {
        text: '未処理',
        variant: 'outline' as const,
        color: 'bg-gray-500',
      };
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 overflow-hidden"
      onClick={e => {
        // モーダル背景クリック時のみ閉じる
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <Card className="w-full max-w-4xl h-[90vh] flex flex-col">
        <CardContent className="p-0 flex flex-col h-full overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b flex-shrink-0">
            <div>
              <h3 className="text-lg font-bold">
                {format(selectedDate, 'yyyy年M月d日(E)', { locale: ja })}
              </h3>
              <p className="text-sm text-gray-600">
                {photos.length}枚の写真
                {currentPhoto && ` - ${formatTime(currentPhoto.capturedAt)}`}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={onClose}>
              <X className="w-4 h-4" />
            </Button>
          </div>

          <div className="flex flex-col lg:flex-row flex-1 overflow-hidden">
            {/* Photo viewer */}
            <div className="flex-1 relative bg-gray-100 overflow-hidden">
              {currentPhoto ? (
                <>
                  <div className="absolute inset-0 flex items-center justify-center p-4">
                    {(() => {
                      const displayImage = getDisplayImage(currentPhoto);
                      return (
                        <img
                          src={displayImage.url}
                          alt={`${format(selectedDate, 'M月d日')}の写真`}
                          className={`
                            max-w-sm max-h-96 object-cover rounded-lg
                            ${displayImage.isGrayscale ? 'filter grayscale' : ''}
                          `}
                        />
                      );
                    })()}
                  </div>

                  {/* Navigation buttons */}
                  {photos.length > 1 && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        className="absolute left-4 top-1/2 transform -translate-y-1/2"
                        onClick={handlePrevPhoto}
                        disabled={currentPhotoIndex === 0}
                      >
                        <ChevronLeft className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="absolute right-4 top-1/2 transform -translate-y-1/2"
                        onClick={handleNextPhoto}
                        disabled={currentPhotoIndex === photos.length - 1}
                      >
                        <ChevronRight className="w-4 h-4" />
                      </Button>
                    </>
                  )}

                  {/* Photo info overlay */}
                  <div className="absolute top-4 left-4 space-y-2">
                    <Badge variant={getStatusBadge(currentPhoto).variant}>
                      {getStatusBadge(currentPhoto).text}
                    </Badge>
                    {currentPhoto.personDetected && (
                      <Badge variant="outline" className="bg-white">
                        <Camera className="w-3 h-3 mr-1" />
                        人物検出
                      </Badge>
                    )}
                  </div>

                  {/* Photo counter */}
                  {photos.length > 1 && (
                    <div className="absolute top-4 right-4 bg-black/70 text-white px-2 py-1 rounded text-sm">
                      {currentPhotoIndex + 1} / {photos.length}
                    </div>
                  )}
                </>
              ) : (
                <div className="h-full flex items-center justify-center">
                  <div className="text-center text-gray-500">
                    <Camera className="w-16 h-16 mx-auto mb-4" />
                    <p>写真がありません</p>
                  </div>
                </div>
              )}
            </div>

            {/* Sidebar - AI detection results and outfit selection */}
            <div className="lg:w-80 w-full lg:h-auto h-64 border-l bg-gray-50 flex flex-col overflow-hidden">
              <div className="p-4 space-y-4 overflow-y-auto flex-1 overscroll-contain">
                {/* AI Detection Status */}
                <div>
                  <h4 className="font-medium mb-2 flex items-center gap-2">
                    <Clock className="w-4 h-4" />
                    AI検出状況
                  </h4>
                  {currentPhoto && (
                    <div className="space-y-2">
                      <div className="text-sm">
                        <span className="font-medium">ステータス: </span>
                        <Badge variant={getStatusBadge(currentPhoto).variant}>
                          {getStatusBadge(currentPhoto).text}
                        </Badge>
                      </div>
                      {currentPhoto.clothingItems &&
                        currentPhoto.clothingItems.length > 0 && (
                          <div className="text-sm">
                            <span className="font-medium">検出アイテム: </span>
                            {currentPhoto.clothingItems.join(', ')}
                          </div>
                        )}
                    </div>
                  )}
                </div>

                {/* Outfit Items */}
                {currentPhoto && (
                  <div>
                    <h4 className="font-medium mb-2 flex items-center gap-2">
                      <Shirt className="w-4 h-4" />
                      選択された服装
                    </h4>

                    {loadingOutfit ? (
                      <div className="text-sm text-gray-500">読み込み中...</div>
                    ) : outfitItems.length > 0 ? (
                      <div className="grid grid-cols-2 gap-2">
                        {outfitItems.slice(0, 4).map(item => (
                          <div
                            key={item.id}
                            className="aspect-square bg-gray-100 rounded-lg overflow-hidden border border-gray-200"
                          >
                            {item.imageUrls && item.imageUrls.length > 0 ? (
                              <img
                                src={item.imageUrls[0]}
                                alt={item.name}
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center bg-gray-200">
                                <Shirt className="w-8 h-8 text-gray-400" />
                              </div>
                            )}
                          </div>
                        ))}
                        {/* 4個未満の場合は空のスロットを埋める */}
                        {Array.from({
                          length: Math.max(0, 4 - outfitItems.length),
                        }).map((_, index) => (
                          <div
                            key={`empty-${index}`}
                            className="aspect-square bg-gray-50 rounded-lg border-2 border-dashed border-gray-300 flex items-center justify-center"
                          >
                            <div className="text-gray-400 text-xs text-center">
                              <Shirt className="w-6 h-6 mx-auto mb-1" />空
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 gap-2">
                        {Array.from({ length: 4 }).map((_, index) => (
                          <div
                            key={`empty-${index}`}
                            className="aspect-square bg-gray-50 rounded-lg border-2 border-dashed border-gray-300 flex items-center justify-center"
                          >
                            <div className="text-gray-400 text-xs text-center">
                              <Shirt className="w-6 h-6 mx-auto mb-1" />空
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Action button */}
                    <Button
                      className="w-full mt-4"
                      onClick={() => {
                        if (onStartClothingSelection) {
                          onStartClothingSelection(currentPhoto);
                        }
                      }}
                      variant={outfitItems.length > 0 ? 'outline' : 'default'}
                    >
                      {outfitItems.length > 0 ? '服装を変更' : '服装を選択'}
                    </Button>
                  </div>
                )}

                {/* AI Detection Results (if available) */}
                {currentPhoto &&
                  currentPhoto.aiDetectionStatus === 'completed' && (
                    <div>
                      <h4 className="font-medium mb-2">AI検出結果</h4>

                      {/* Annotation Image */}
                      {currentPhoto.aiAnnotationImageUrl && (
                        <div className="mb-3">
                          <p className="text-sm text-gray-600 mb-2">
                            検出結果（アノテーション画像）:
                          </p>
                          <div className="bg-white rounded border border-gray-200 overflow-hidden">
                            <img
                              src={`${apiUrl}${currentPhoto.aiAnnotationImageUrl}`}
                              alt="AI検出結果"
                              className="w-full h-auto object-contain max-h-48"
                              onError={e => {
                                logger.error(
                                  'Annotation image failed to load:',
                                  currentPhoto.aiAnnotationImageUrl
                                );
                                e.currentTarget.style.display = 'none';
                              }}
                            />
                          </div>
                        </div>
                      )}

                      {/* Detection Summary */}
                      <div className="bg-white p-3 rounded border border-gray-200 space-y-2">
                        <div className="text-sm">
                          <span className="font-medium">人物検出:</span>
                          <Badge
                            variant={
                              currentPhoto.personDetected
                                ? 'default'
                                : 'secondary'
                            }
                            className="ml-2"
                          >
                            {currentPhoto.personDetected
                              ? '検出済'
                              : '未検出'}
                          </Badge>
                        </div>

                        {currentPhoto.confidenceScore && (
                          <div className="text-sm">
                            <span className="font-medium">信頼度:</span>
                            <span className="ml-2">
                              {(currentPhoto.confidenceScore * 100).toFixed(1)}%
                            </span>
                          </div>
                        )}

                        {currentPhoto.clothingItems &&
                          currentPhoto.clothingItems.length > 0 && (
                            <div className="text-sm">
                              <span className="font-medium">検出アイテム:</span>
                              <div className="mt-1 flex flex-wrap gap-1">
                                {currentPhoto.clothingItems.map(
                                  (item, index) => (
                                    <Badge
                                      key={index}
                                      variant="outline"
                                      className="text-xs"
                                    >
                                      {item}
                                    </Badge>
                                  )
                                )}
                              </div>
                            </div>
                          )}
                      </div>

                      {/* Raw Detection Results (if available) */}
                      {currentPhoto.aiDetectionResults && (
                        <div className="mt-3">
                          <details className="text-xs">
                            <summary className="font-medium cursor-pointer text-gray-600 hover:text-gray-800">
                              詳細データを表示
                            </summary>
                            <div className="bg-gray-50 p-2 rounded border border-gray-200 mt-2 overflow-auto max-h-32">
                              <pre className="text-xs">
                                {JSON.stringify(
                                  currentPhoto.aiDetectionResults,
                                  null,
                                  2
                                )}
                              </pre>
                            </div>
                          </details>
                        </div>
                      )}
                    </div>
                  )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
