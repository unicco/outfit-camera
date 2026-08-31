import { useEffect, useRef } from 'react';

interface UseTouchOptions {
  onTap?: () => void;
  onLongPress?: () => void;
  longPressDelay?: number;
  preventDefault?: boolean;
}

export function useTouch(
  elementRef: React.RefObject<HTMLElement>,
  options: UseTouchOptions = {}
) {
  const {
    onTap,
    onLongPress,
    longPressDelay = 500,
    preventDefault = true,
  } = options;

  const touchTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isTouchingRef = useRef(false);
  const isLongPressRef = useRef(false);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    const handleTouchStart = (e: TouchEvent) => {
      if (preventDefault) {
        e.preventDefault();
      }

      isTouchingRef.current = true;
      isLongPressRef.current = false;

      if (onLongPress) {
        touchTimerRef.current = setTimeout(() => {
          if (isTouchingRef.current) {
            isLongPressRef.current = true;
            onLongPress();
          }
        }, longPressDelay);
      }
    };

    const handleTouchEnd = (e: TouchEvent) => {
      if (preventDefault) {
        e.preventDefault();
      }

      if (touchTimerRef.current) {
        clearTimeout(touchTimerRef.current);
        touchTimerRef.current = null;
      }

      if (isTouchingRef.current && !isLongPressRef.current && onTap) {
        onTap();
      }

      isTouchingRef.current = false;
      isLongPressRef.current = false;
    };

    const handleTouchCancel = () => {
      if (touchTimerRef.current) {
        clearTimeout(touchTimerRef.current);
        touchTimerRef.current = null;
      }

      isTouchingRef.current = false;
      isLongPressRef.current = false;
    };

    // タッチイベントリスナーを追加
    element.addEventListener('touchstart', handleTouchStart, {
      passive: !preventDefault,
    });
    element.addEventListener('touchend', handleTouchEnd, {
      passive: !preventDefault,
    });
    element.addEventListener('touchcancel', handleTouchCancel);

    // マウスイベントもサポート（開発時のテスト用）
    const handleMouseDown = (e: MouseEvent) => {
      // タッチデバイスでない場合のみ処理
      if ('ontouchstart' in window) return;
      handleTouchStart(e as unknown as TouchEvent);
    };

    const handleMouseUp = (e: MouseEvent) => {
      // タッチデバイスでない場合のみ処理
      if ('ontouchstart' in window) return;
      handleTouchEnd(e as unknown as TouchEvent);
    };

    element.addEventListener('mousedown', handleMouseDown);
    element.addEventListener('mouseup', handleMouseUp);
    element.addEventListener('mouseleave', handleTouchCancel);

    return () => {
      element.removeEventListener('touchstart', handleTouchStart);
      element.removeEventListener('touchend', handleTouchEnd);
      element.removeEventListener('touchcancel', handleTouchCancel);
      element.removeEventListener('mousedown', handleMouseDown);
      element.removeEventListener('mouseup', handleMouseUp);
      element.removeEventListener('mouseleave', handleTouchCancel);

      if (touchTimerRef.current) {
        clearTimeout(touchTimerRef.current);
      }
    };
  }, [elementRef, onTap, onLongPress, longPressDelay, preventDefault]);
}
