import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';

export function GooglePhotosCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');
  const [message, setMessage] = useState<string>('認証処理中...');

  useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams.get('code');
      const error = searchParams.get('error');

      if (error) {
        setStatus('error');
        setMessage(`認証エラー: ${error}`);
        setTimeout(() => navigate('/'), 3000);
        return;
      }

      if (!code) {
        setStatus('error');
        setMessage('認証コードが見つかりません');
        setTimeout(() => navigate('/'), 3000);
        return;
      }

      try {
        // バックエンドにコードを送信
        await apiClient.get<string>(
          `/api/v2/google-photos/oauth2callback?code=${encodeURIComponent(code)}`,
          { skipTransform: true }
        );

        setStatus('success');
        setMessage('Google Photos の認証が完了しました！');
        setTimeout(() => navigate('/'), 2000);
      } catch (err) {
        logger.error('OAuth callback error:', err);
        setStatus('error');
        setMessage('認証処理中にエラーが発生しました');
        setTimeout(() => navigate('/'), 3000);
      }
    };

    handleCallback();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
        <div className="text-center">
          {status === 'processing' && (
            <>
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">{message}</p>
            </>
          )}

          {status === 'success' && (
            <>
              <div className="text-green-600 mb-4">
                <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-gray-800 font-medium">{message}</p>
              <p className="text-gray-600 text-sm mt-2">ホーム画面に戻ります...</p>
            </>
          )}

          {status === 'error' && (
            <>
              <div className="text-red-600 mb-4">
                <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <p className="text-gray-800 font-medium">{message}</p>
              <p className="text-gray-600 text-sm mt-2">ホーム画面に戻ります...</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
