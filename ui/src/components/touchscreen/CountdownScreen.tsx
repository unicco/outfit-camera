import React, { useState, useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { logger } from '@/utils/logger';

interface CountdownScreenProps {
  onCountdownComplete: () => void;
  onCancel: () => void;
  countdownSeconds?: number;
  cameraUrl?: string;
}

export const CountdownScreen: React.FC<CountdownScreenProps> = ({
  onCountdownComplete,
  onCancel,
  countdownSeconds = 7,
  cameraUrl,
}) => {
  const [count, setCount] = useState(() => countdownSeconds);
  const [showPreview, setShowPreview] = useState(true);
  const [streamError, setStreamError] = useState(false);
  const isCountdownActive = useRef(false);

  useEffect(() => {
    // カウントダウンがアクティブでない場合は開始
    if (!isCountdownActive.current) {
      isCountdownActive.current = true;
      logger.dev('🎬 Starting countdown from', count);
    }

    if (count === 0) {
      onCountdownComplete();
      return;
    }

    const timer = setTimeout(() => {
      logger.dev('🕒 Countdown:', count - 1);
      setCount(count - 1);
    }, 1000);

    return () => clearTimeout(timer);
  }, [count, onCountdownComplete]);

  return (
    <div className="h-full relative overflow-hidden">
      {/* Background - Camera preview */}
      <div className="absolute inset-0">
        {showPreview && !streamError ? (
          <img
            src={`${cameraUrl}/stream`}
            alt="Camera Preview"
            className="w-full h-full object-cover"
            onError={() => {
              logger.error('Camera stream error during countdown');
              setStreamError(true);
              setShowPreview(false);
            }}
            onLoad={() => {
              logger.dev('Camera stream loaded during countdown');
              setStreamError(false);
            }}
          />
        ) : (
          // Fallback gradient background
          <div className="w-full h-full bg-gradient-to-br from-gray-800 to-gray-900" />
        )}

      {/* Dark overlay for countdown visibility */}
      <div className="absolute inset-0 bg-black/40" />
    </div>

    {/* Cancel button */}
    <button
      onClick={onCancel}
      className="absolute top-6 right-6 p-2 rounded-full bg-gray-800/80 hover:bg-gray-700 hover:bg-gray-800/90 transition-colors z-20"
      style={{ touchAction: 'manipulation' }}
    >
      <X className="w-5 h-5 text-white" />
    </button>

      {/* Countdown display */}
      <div className="relative h-full flex items-center justify-center z-10">
        <div className="text-center">
          <div className="text-[150px] font-bold text-white animate-pulse drop-shadow-2xl">
            {count}
          </div>
          <div className="text-lg text-white mt-3 drop-shadow-lg px-4">
            全身が写るよう立ってください
          </div>
        </div>
      </div>

      {/* Live indicator */}
      {showPreview && !streamError && (
        <div className="absolute top-6 left-6 flex items-center gap-1 bg-red-600/90 text-white px-2 py-1 rounded-full z-20">
          <div className="w-1.5 h-1.5 bg-white rounded-full animate-pulse"></div>
          <span className="text-xs font-medium">LIVE</span>
        </div>
      )}
    </div>
  );
};
