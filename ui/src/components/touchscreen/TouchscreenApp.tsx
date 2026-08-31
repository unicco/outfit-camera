import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MorningBriefScreen } from './MorningBriefScreen';
import { CountdownScreen } from './CountdownScreen';
import { PreviewScreen } from './PreviewScreen';
import { CompleteScreen } from './CompleteScreen';
import { API_TIMEOUT } from '@/config/api';
import { apiClient, ApiClient, ApiRequestOptions, ApiError } from '@/services/apiClient';
import { logger } from '@/utils/logger';

type ScreenState = 'standby' | 'countdown' | 'preview' | 'complete';

interface TouchscreenAppProps {
  apiUrl: string;
  cameraUrl: string;
  debugMode?: boolean;
}

export const TouchscreenApp: React.FC<TouchscreenAppProps> = ({
  apiUrl,
  cameraUrl,
  debugMode = false,
}) => {
  const cameraStreamUrl = cameraUrl;
  const [currentScreen, setCurrentScreen] = useState<ScreenState>('standby');
  const [capturedPhoto, setCapturedPhoto] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDisplayOn, setIsDisplayOn] = useState(true);
  const [lastActivityTime, setLastActivityTime] = useState(() => Date.now());
  const [personDetected, setPersonDetected] = useState(false);
  const [cameraServiceAvailable, setCameraServiceAvailable] = useState(false);
  const displayTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  // 物理バックライトの起こし直しを送った最終時刻（連打スロットル用）
  const lastWakeSentRef = useRef<number>(0);

  // カメラサービス用のAPIクライアント
  const cameraClient = useRef<ApiClient>(new ApiClient(cameraUrl));
  useEffect(() => {
    cameraClient.current = new ApiClient(cameraUrl);
  }, [cameraUrl]);

  // Integrated display timer reset functionality
  const resetDisplayTimer = useCallback(() => {
    setLastActivityTime(Date.now());
    setIsDisplayOn(true);

    if (displayTimeoutRef.current) {
      clearTimeout(displayTimeoutRef.current);
      displayTimeoutRef.current = null;
    }
  }, []);

  // カメラサービスが利用可能かチェック
  useEffect(() => {
    const checkCameraService = async () => {
      try {
        const response = await cameraClient.current.get('/health');
        setCameraServiceAvailable(!!response);
      } catch {
        setCameraServiceAvailable(false);
      }
    };
    checkCameraService();
  }, [cameraUrl]);

  // PIR sensor polling for person detection
  useEffect(() => {
    // カメラサービスが利用不可の場合はPIRポーリングをスキップ
    if (!cameraServiceAvailable) {
      return;
    }

    const pollPIRStatus = async () => {
      try {
        // カメラサービス専用のクライアントを使用
        const pirData = await cameraClient.current.get<{
          enabled: boolean;
          detectionsCount: number;
        }>('/pir/status');

        // PIRが無効の場合は何もしない
        if (!pirData.enabled) {
          return;
        }

        const detected = pirData.detectionsCount > 0;

        if (detected) {
          // カウントダウン中はPIR検知を無視
          if (currentScreen !== 'countdown') {
            logger.dev('🔥 PIR DETECTED - Force reset timer (detections:', pirData.detectionsCount, ')');
            setPersonDetected(true);
            setIsDisplayOn(true); // PIR検知時にディスプレイをオンにする
            resetDisplayTimer();
          }
        } else {
          setPersonDetected(false);
        }
      } catch {
        // PIR ポーリングのエラーはログに出さない。カメラサービスが無い環境では常に失敗する
      }
    };

    const pollInterval = setInterval(pollPIRStatus, 500);
    return () => clearInterval(pollInterval);
  }, [personDetected, resetDisplayTimer, cameraUrl, currentScreen, cameraServiceAvailable]);

  // Display timeout management - 検証用に無効化
  useEffect(() => {
    if (displayTimeoutRef.current) {
      clearTimeout(displayTimeoutRef.current);
      displayTimeoutRef.current = null;
    }

    // スタンバイ画面以外ではタイムアウト無効
    if (currentScreen === 'standby') {
      // 現在はPIRが無効なので、単純なタイマーのみ
      const checkAndSetTimeout = () => {
        const timeSinceLastActivity = Date.now() - lastActivityTime;
        const remainingTime = 30000 - timeSinceLastActivity;

        if (remainingTime <= 0) {
          logger.dev('💀 Display timeout triggered - turning off');
          setIsDisplayOn(false);
        } else {
          displayTimeoutRef.current = setTimeout(() => {
            logger.dev('💀 Display timeout after 30s - turning off');
            setIsDisplayOn(false);
          }, remainingTime);
        }
      };

      checkAndSetTimeout();
    }

    return () => {
      if (displayTimeoutRef.current) {
        clearTimeout(displayTimeoutRef.current);
        displayTimeoutRef.current = null;
      }
    };
  }, [currentScreen, lastActivityTime, personDetected]);

  // User activity listeners
  useEffect(() => {
    // 物理バックライトをタッチで起こす（PIR 以外の復帰経路）。
    // camera service 側はバックライトを PIR モーションでしか点灯しないため、
    // タッチ時に /display/on を叩いて物理的に点灯させる。3 秒スロットルで連打を抑制。
    const wakePhysicalDisplay = () => {
      const now = Date.now();
      if (now - lastWakeSentRef.current < 3000) {
        return;
      }
      lastWakeSentRef.current = now;
      cameraClient.current.post('/display/on', undefined, { timeout: 3000 }).catch(() => {
        // camera service 不在時は無視（ローカル state のみ更新する）
      });
    };

    const handleUserAction = () => {
      resetDisplayTimer();
      wakePhysicalDisplay();
    };

    window.addEventListener('touchstart', handleUserAction);
    window.addEventListener('click', handleUserAction);
    window.addEventListener('keydown', handleUserAction);
    window.addEventListener('mousemove', handleUserAction);

    return () => {
      window.removeEventListener('touchstart', handleUserAction);
      window.removeEventListener('click', handleUserAction);
      window.removeEventListener('keydown', handleUserAction);
      window.removeEventListener('mousemove', handleUserAction);
    };
  }, [resetDisplayTimer, cameraUrl]);

  const handleCaptureStart = () => {
    setCurrentScreen('countdown');
    resetDisplayTimer();
  };

  const handleCountdownComplete = async () => {
    try {
      const captureUrl = cameraUrl;

      logger.dev('📷 撮影開始 - captureUrl:', captureUrl);

      const options: ApiRequestOptions = {
        // 撮影は解像度切替 + 露出安定待ち（0.5s）があるため長めに設定
        // ApiClient 内部の DEFAULT(5s) では不足するケースがある
        timeout: 15000,
      };

      // カメラサービス専用のクライアントを使用
      // 撮影のみ実行（アップロードは保存ボタン押下時）
      const data = await cameraClient.current.post<{
        status?: string;
        filename?: string;
        photoUrl?: string;
        message?: string;
      }>('/capture?force=true', undefined, options);

      logger.dev('📷 撮影レスポンス 成功');
      logger.dev('📷 撮影成功 - データ:', data);

      const photoFilename = data.photoUrl || data.filename;
      logger.dev('📷 撮影データ:', data);
      logger.dev('📷 captureUrl:', captureUrl);
      logger.dev('📷 photoFilename:', photoFilename);

      // カメラサービスは撮影に失敗しても例外でなく 200 で {"status": "failed"} を返す。
      // ここで弾かないとファイル名の無いまま preview へ進み、存在しない写真を掴む
      if (data.status !== 'success' || !photoFilename) {
        throw new Error(data.message || 'カメラサービスが写真を返しませんでした');
      }

      const fullPhotoUrl = `${captureUrl}/photos/${photoFilename.split('/').pop()}`;
      logger.dev('📷 構築した完全URL:', fullPhotoUrl);

      logger.dev('📷 設定する capturedPhoto:', fullPhotoUrl);
      setCapturedPhoto(fullPhotoUrl);
      logger.dev('📷 画面をpreviewに変更');
      setCurrentScreen('preview');
    } catch (error) {
      logger.error('撮影エラー詳細:', error);
      logger.error('撮影エラータイプ:', typeof error);
      logger.error(
        '撮影エラーメッセージ:',
        error instanceof Error ? error.message : String(error)
      );

      alert(
        `撮影に失敗しました: ${error instanceof Error ? error.message : String(error)}`
      );
      setTimeout(() => {
        setCurrentScreen('standby');
      }, 1000);
    }
  };

  const handleCountdownCancel = () => {
    setCurrentScreen('standby');
    resetDisplayTimer();
  };

  const handleSavePhoto = async () => {
    if (!capturedPhoto || isSaving) return;

    setIsSaving(true);

    try {
      logger.dev('📤 Starting photo save process...');

      // Get the photo from camera service
      // 画像バイナリデータの取得のため fetch() を直接使用
      logger.dev('📥 Fetching photo from:', capturedPhoto);

      // eslint-disable-next-line no-restricted-globals
      const imageResponse = await fetch(capturedPhoto);
      logger.dev('📥 Fetch response status:', imageResponse.status);

      if (!imageResponse.ok) {
        throw new Error(`写真の取得に失敗しました (status: ${imageResponse.status}, url: ${capturedPhoto})`);
      }

      const imageBlob = await imageResponse.blob();
      logger.dev('📥 Image blob size:', imageBlob.size, 'bytes');

      const filename = capturedPhoto.split('/').pop() || 'touchscreen_photo.jpg';
      logger.dev('📥 Filename:', filename);

      // FormData を作成して画像をアップロード
      const formData = new FormData();
      formData.append('file', imageBlob, filename);
      // 経路を API に名乗る。Pi の再送（source=camera_retry）と DB 上で区別するため
      formData.append('source', 'touchscreen');

      const uploadOptions: ApiRequestOptions = {
        skipTransform: true,
        timeout: API_TIMEOUT.FILE_UPLOAD,
      };

      let uploadResult;
      try {
        logger.dev('📤 Sending upload request to API...');
        uploadResult = await apiClient.post('/api/v2/upload', formData, uploadOptions);
        logger.dev('✅ Upload response received:', {
          status: 'success',
          data: uploadResult,
        });
      } catch (uploadError: unknown) {
        logger.error('❌ Upload error occurred:', uploadError);

        const error = uploadError instanceof Error
          ? uploadError
          : new Error('アップロード中にエラーが発生しました。');

        const errorCode =
          (uploadError as { code?: string } | undefined)?.code ?? null;
        const status =
          (uploadError as ApiError | undefined)?.status ??
          ((uploadError as { response?: { status?: number } } | undefined)?.response?.status ?? null);

        if (error.name === 'NetworkError' || errorCode === 'ECONNREFUSED') {
          throw Object.assign(
            new Error('ネットワーク接続エラーが発生しました。接続を確認してください。'),
            { cause: error }
          );
        }
        if (error.name === 'TimeoutError' || errorCode === 'ETIMEDOUT') {
          throw Object.assign(
            new Error('アップロードがタイムアウトしました。もう一度お試しください。'),
            { cause: error }
          );
        }
        if (status === 413) {
          throw Object.assign(new Error('ファイルサイズが大きすぎます。'), { cause: error });
        }
        if (status === 507) {
          throw Object.assign(new Error('サーバーの容量が不足しています。'), { cause: error });
        }

        throw Object.assign(new Error(error.message || 'アップロード中にエラーが発生しました。'), {
          cause: error,
        });
      }
      logger.dev('✅ Photo uploaded successfully:', uploadResult);

      setCurrentScreen('complete');

      // 撮影完了後は3秒表示してからディスプレイを完全オフにする
      setTimeout(async () => {
        setCapturedPhoto(null);

        // ディスプレイを完全オフ（UIとカメラサービス両方）
        logger.dev(
          '📤 Turning off display completely after photo completion...'
        );
        setIsDisplayOn(false); // UI: 黒画面
        setCurrentScreen('standby'); // スタンバイ状態に戻す

        try {
          // カメラサービス専用のクライアントを使用
          const options: ApiRequestOptions = {
            timeout: API_TIMEOUT.DEFAULT,
          };

          await cameraClient.current.post('/display/off', undefined, options);

          logger.dev(
            '✅ Display turned off successfully - brightness=0, bl_power=1, Chromium terminated'
          );
        } catch (error) {
          logger.error('❌ Error requesting display turn off:', error);
          // エラーが発生してもUIの処理は継続する
        }

        // 一連の撮影処理（GCS/Google Photos アップロード）が完了したので Pi を halt する。
        // この時点で画像は GCS に永続化済、Google Photos アップロードは VPS 側で継続する
        // ため、Pi の halt では中断されない。camera service 側は AUTO_SHUTDOWN_ENABLED!=true
        // のとき no-op で返す。halt に失敗しても毎日 cutoff（20:00）が保険として落とす。
        try {
          await cameraClient.current.post('/shutdown', undefined, {
            timeout: API_TIMEOUT.DEFAULT,
          });
          logger.dev('⏻ Shutdown requested after capture+upload completed');
        } catch (error) {
          logger.error('❌ Error requesting shutdown:', error);
        }

        // ディスプレイオフ時にスタンバイ状態に戻すことで、
        // 次回ディスプレイ点灯時に確実にスタンバイ画面が表示される
      }, 3000);
    } catch (error) {
      logger.error('保存エラー:', error);
      logger.error('エラーの詳細:', {
        name: error instanceof Error ? error.name : 'Unknown',
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : 'No stack trace',
      });

      let errorMessage = '保存に失敗しました';
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          errorMessage = 'アップロードがタイムアウトしました（30秒）';
        } else if (error.message.includes('fetch')) {
          errorMessage = `写真の取得に失敗: ${error.message}`;
        } else if (error.message.includes('network')) {
          errorMessage = `ネットワークエラー: ${error.message}`;
        } else {
          errorMessage = error.message;
        }
      }
      alert(`エラー: ${errorMessage}\n\n詳細: ${error instanceof Error ? error.stack : String(error)}`);

      logger.dev('エラーのため preview 画面に留まります');
    } finally {
      setIsSaving(false);
    }
  };

  const handleRetake = () => {
    // 捨てた写真はカメラサービス側の未送信マークも外す。外さないと再送ループが拾って、
    // 捨てたはずの写真がその日の記録に並ぶ
    if (capturedPhoto) {
      const filename = capturedPhoto.split('/').pop();
      if (filename) {
        // await しない。撮り直しの操作を通信で待たせない（失敗しても、この写真が
        // 記録に載る従来の挙動に戻るだけ）
        cameraClient.current
          .post(`/photo/${filename}/discard`, undefined, {
            timeout: API_TIMEOUT.DEFAULT,
          })
          .catch((error) => {
            logger.error('❌ Failed to discard retaken photo:', error);
          });
      }
    }

    setCapturedPhoto(null);
    setCurrentScreen('standby');
    resetDisplayTimer();
  };

  const handleReloadTouchscreen = useCallback(() => {
    logger.dev('Touchscreen requested manual reload');
    window.location.reload();
  }, []);

  // Display off state
  if (!isDisplayOn) {
    return <div className="fixed inset-0 bg-black" />;
  }

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ width: '480px' }}>
      {/* Development controls */}
      {debugMode && (
        <div className="absolute top-4 right-4 z-50 space-y-2">
          <div className="flex space-x-2">
            <button
              onClick={() => {
                setPersonDetected(true);
                resetDisplayTimer();
                logger.dev('Person detected - Display activated');
              }}
              className="px-3 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700"
            >
              👤 Person
            </button>
            <button
              onClick={() => {
                setPersonDetected(false);
                logger.dev(
                  'Person lost - Display will turn off in 30 seconds if no activity'
                );
              }}
              className="px-3 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700"
            >
              🚶 Gone
            </button>
          </div>
          <div className="bg-gray-800 text-white text-xs rounded p-2 max-w-xs">
            <div>
              Person: {personDetected ? '👤' : '❌'} | Display:{' '}
              {isDisplayOn ? '💡' : '🌙'}
            </div>
            <div className="mt-1">API: {apiUrl}</div>
            <div>Camera: {cameraUrl}</div>
            <div>
              PIR Detections: {personDetected ? '👤 Active' : '❌ None'}
            </div>
          </div>
        </div>
      )}

      {currentScreen === 'standby' && (
        <MorningBriefScreen
          onCaptureStart={handleCaptureStart}
          onReloadTouchscreen={handleReloadTouchscreen}
        />
      )}
      {currentScreen === 'countdown' && (
        <CountdownScreen
          onCountdownComplete={handleCountdownComplete}
          onCancel={handleCountdownCancel}
          cameraUrl={cameraStreamUrl}
          countdownSeconds={7}
        />
      )}
      {currentScreen === 'preview' && capturedPhoto && (
        <PreviewScreen
          photoUrl={capturedPhoto}
          onSave={handleSavePhoto}
          onRetake={handleRetake}
          isSaving={isSaving}
        />
      )}
      {debugMode && (
        <div className="absolute bottom-4 left-4 bg-black/75 text-white p-2 text-xs rounded z-50">
          Screen: {currentScreen} | Photo: {capturedPhoto ? 'あり' : 'なし'} |
          Saving: {isSaving ? 'Yes' : 'No'}
        </div>
      )}
      {currentScreen === 'complete' && <CompleteScreen />}
    </div>
  );
};
