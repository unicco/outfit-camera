import { TouchscreenApp } from '@/components/touchscreen';
import { API_URL, CAMERA_URL } from '@/config/urls';
import { logger } from '@/utils/logger';

export function TouchscreenPage() {
  logger.dev('TouchscreenPage component rendered with centralized config');
  logger.dev('📡 Using URLs:', { API_URL, CAMERA_URL });

  // デバッグモードの判定
  const isDebugMode =
    new URLSearchParams(window.location.search).get('mode') === 'debug';

  return (
    <div className="min-h-screen bg-black">
      <TouchscreenApp
        apiUrl={API_URL}
        cameraUrl={CAMERA_URL}
        debugMode={isDebugMode}
      />
    </div>
  );
}
