import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';
import { Loader2, CheckCircle, XCircle, ExternalLink, Settings, RefreshCcw } from 'lucide-react';
import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';


interface AuthStatus {
  is_authenticated: boolean;
  album_name?: string;
}


export default function GooglePhotosSettings() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>({ is_authenticated: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);

  // Google Photos 認証状態を取得
  const fetchAuthStatus = async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await apiClient.get<AuthStatus>('/api/v2/google-photos/auth-status');
      setAuthStatus(data);
    } catch (err) {
      logger.error('Failed to fetch auth status:', err);
      setError(err instanceof Error ? err.message : '認証状態の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  // Google Photos 認証を開始
  const handleAuthenticate = async () => {
    setIsAuthenticating(true);
    setError(null);

    try {
      // 認証 URL を取得
      const data = await apiClient.get<{ auth_url: string }>('/api/v2/google-photos/auth-url');

      // 新しいタブで認証ページを開く
      window.open(data.auth_url, '_blank');

      // 認証完了の確認を開始（ポーリング）
      const checkInterval = setInterval(async () => {
        try {
          const statusData = await apiClient.get<AuthStatus>('/api/v2/google-photos/auth-status');
          if (statusData.is_authenticated) {
            setAuthStatus(statusData);
            setIsAuthenticating(false);
            clearInterval(checkInterval);
            setError(null);
          }
        } catch (err) {
          logger.error('Auth status check failed:', err);
        }
      }, 2000); // 2秒ごとに確認

      // 2分後にポーリングを停止
      setTimeout(() => {
        clearInterval(checkInterval);
        setIsAuthenticating(false);
      }, 120000);

    } catch (err) {
      logger.error('Authentication failed:', err);
      setError(err instanceof Error ? err.message : '認証に失敗しました');
      setIsAuthenticating(false);
    }
  };

  // ログアウト処理
  const handleLogout = async () => {
    setLoading(true);
    setError(null);

    try {
      await apiClient.post('/api/v2/google-photos/logout');
      setAuthStatus({ is_authenticated: false });
      setError(null);
    } catch (err) {
      logger.error('Logout failed:', err);
      setError(err instanceof Error ? err.message : 'ログアウトに失敗しました');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- マウント時の認証状態取得（fetchAuthStatus 内部で setState）
    fetchAuthStatus();
  }, []);

  if (loading && !isAuthenticating) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Google Photos 連携
          </CardTitle>
          <CardDescription>
            撮影した写真を Google Photos にも保存できます
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span className="ml-2">読み込み中...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Settings className="h-5 w-5" />
          Google Photos 連携
        </CardTitle>
        <CardDescription>
          撮影した写真を Google Photos にも保存できます
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 認証状態の表示 */}
        <div className="flex items-center gap-2">
          {authStatus.is_authenticated ? (
            <>
              <CheckCircle className="h-5 w-5 text-green-500" />
              <span className="text-green-700 font-medium">認証済</span>
              {authStatus.album_name && (
                <span className="text-sm text-gray-600">
                  アルバム: {authStatus.album_name}
                </span>
              )}
            </>
          ) : (
            <>
              <XCircle className="h-5 w-5 text-gray-400" />
              <span className="text-gray-600">未認証</span>
            </>
          )}
        </div>

        {/* エラー表示 */}
        {error && (
          <Alert variant="destructive">
            <XCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* 認証中の表示 */}
        {isAuthenticating && (
          <Alert>
            <Loader2 className="h-4 w-4 animate-spin" />
            <AlertDescription>
              認証ページが新しいタブで開きました。Google で認証を完了してください。
              認証が完了すると自動的に更新されます。
            </AlertDescription>
          </Alert>
        )}

        {/* 認証ボタン */}
        <div className="flex flex-wrap gap-2">
          {!authStatus.is_authenticated ? (
            <Button
              onClick={handleAuthenticate}
              disabled={isAuthenticating || loading}
              className="flex items-center gap-2"
            >
              {isAuthenticating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ExternalLink className="h-4 w-4" />
              )}
              Google Photos 認証
            </Button>
          ) : (
            <>
              <Button
                onClick={handleAuthenticate}
                disabled={isAuthenticating || loading}
                variant="secondary"
                className="flex items-center gap-2"
              >
                {isAuthenticating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCcw className="h-4 w-4" />
                )}
                Google Photos 再認証
              </Button>
              <Button
                variant="outline"
                onClick={handleLogout}
                disabled={loading || isAuthenticating}
                className="flex items-center gap-2"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                認証解除
              </Button>
            </>
          )}

          <Button
            variant="outline"
            onClick={fetchAuthStatus}
            disabled={loading || isAuthenticating}
            className="flex items-center gap-2"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Settings className="h-4 w-4" />
            )}
            状態を更新
          </Button>
        </div>

        {/* 説明 */}
        <div className="text-sm text-gray-600 space-y-2">
          <p>
            <strong>機能:</strong> 「保存」ボタンを押すと、写真が Google Photos にも自動的にアップロードされます。
          </p>
          <p>
            <strong>注意:</strong> プレビュー段階では保存されず、明確に「保存」ボタンを押した写真のみが Google Photos に保存されます。
          </p>
          <p>
            <strong>再認証:</strong> リフレッシュトークンは 7 日で失効するため、必要に応じて「Google Photos 再認証」からいつでも更新できます。
          </p>
          {authStatus.is_authenticated && (
            <p>
              <strong>アルバム:</strong> 「{authStatus.album_name || 'Coordinate Records'}」に保存されます。
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
