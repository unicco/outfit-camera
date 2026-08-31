import React, { useState } from 'react';
import { X, AlertCircle } from 'lucide-react';
import { logger } from '@/utils/logger';

interface PreviewScreenProps {
  photoUrl: string;
  onSave: () => void;
  onRetake: () => void;
  isSaving?: boolean;
}

export const PreviewScreen: React.FC<PreviewScreenProps> = ({
  photoUrl,
  onSave,
  onRetake,
  isSaving = false,
}) => {
  const [imageLoading, setImageLoading] = useState(true);
  const [imageError, setImageError] = useState(false);

  // 画像URLの処理を簡素化（TouchscreenAppで完全なURLが渡される）
  logger.dev('🖼️ PreviewScreen に渡された photoUrl:', photoUrl);
  const imageUrl = photoUrl;

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    logger.dev('Preview image loaded successfully:', imageUrl);
    logger.dev(
      'Preview dimensions:',
      (e.target as HTMLImageElement).naturalWidth,
      'x',
      (e.target as HTMLImageElement).naturalHeight
    );
    setImageLoading(false);
    setImageError(false);
  };

  const handleImageError = () => {
    logger.error('Preview image failed to load:', imageUrl);
    setImageLoading(false);
    setImageError(true);
  };

  return (
    <div className="h-full relative bg-black">
      {/* Loading indicator */}
      {imageLoading && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-gray-900"
          style={{ width: '480px' }}
        >
          <div className="text-center">
            <div className="w-12 h-12 border-4 border-white border-t-transparent rounded-full animate-spin mb-4 mx-auto"></div>
            <p className="text-white text-lg">画像を読み込み中...</p>
          </div>
        </div>
      )}

      {/* Error display */}
      {imageError && !imageLoading && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-gray-900"
          style={{ width: '480px' }}
        >
          <div className="text-center">
            <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
            <p className="text-white text-lg mb-2">
              画像の読み込みに失敗しました
            </p>
            <p className="text-gray-400 text-sm mb-6">パス: {imageUrl}</p>
            <button
              onClick={onRetake}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg transition-colors"
              style={{ touchAction: 'manipulation' }}
            >
              再撮影する
            </button>
          </div>
        </div>
      )}

      {/* Main image */}
      {!imageError && (
        <img
          src={imageUrl}
          alt="撮影した写真"
          className="w-full h-full object-cover"
          onLoad={handleImageLoad}
          onError={handleImageError}
          style={{
            display: imageLoading ? 'none' : 'block',
          }}
        />
      )}

      {/* Controls - only show if image loaded successfully */}
      {!imageError && !imageLoading && (
        <>
          {/* 右上のバツボタン */}
          <button
            onClick={onRetake}
            aria-label="撮り直す"
            className="absolute top-6 right-6 p-3 rounded-full bg-gray-600/90 hover:bg-gray-700 hover:bg-gray-600/95 transition-all transform active:scale-95 shadow-lg z-20"
            style={{ touchAction: 'manipulation' }}
          >
            <X className="w-7 h-7 text-white" />
          </button>

          {/* 下部の保存ボタン */}
          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent">
            <button
              onClick={onSave}
              disabled={isSaving}
              className={`w-full flex items-center justify-center py-5 text-white text-xl font-bold transition-all transform min-h-[65px] shadow-xl hover:shadow-2xl ${
                isSaving
                  ? 'bg-gray-600 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700 active:bg-blue-800 active:scale-95'
              }`}
              style={{ touchAction: 'manipulation' }}
            >
              {isSaving ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></div>
                  保存中...
                </>
              ) : (
                '保存'
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
};
