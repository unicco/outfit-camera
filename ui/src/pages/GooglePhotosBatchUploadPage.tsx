import React, { useRef, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  CalendarClock,
  CheckCircle2,
  Info,
  Loader2,
  MapPin,
  Trash2,
  UploadCloud,
  XCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  createBatchUploadFormData,
  uploadGooglePhotosBatch,
  type GooglePhotosBatchUploadResponse,
} from '@/services/googlePhotos';
import { logger } from '@/utils/logger';

type UploadStatus = 'idle' | 'uploading' | 'success' | 'error';

interface SelectedPhoto {
  id: string;
  file: File;
  previewUrl: string;
  captureTime: string;
  locationName: string;
  latitude: string;
  longitude: string;
  status: UploadStatus;
  error?: string;
  mediaItemId?: string;
}

const generateClientId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
};

const parseCoordinate = (value: string): number | null => {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
};

const toIsoStringOrNull = (value: string): string | null => {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
};

const GooglePhotosBatchUploadPage: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [photos, setPhotos] = useState<SelectedPhoto[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [globalMessage, setGlobalMessage] = useState<string | null>(null);

  const [bulkCaptureTime, setBulkCaptureTime] = useState('');
  const [bulkLocationName, setBulkLocationName] = useState('');
  const [bulkLatitude, setBulkLatitude] = useState('');
  const [bulkLongitude, setBulkLongitude] = useState('');

  const activeCount = useMemo(() => photos.filter(photo => photo.status === 'success').length, [photos]);

  const handleBack = () => {
    navigate('/');
  };

  const cleanupPreviewUrl = (url?: string) => {
    if (url) {
      URL.revokeObjectURL(url);
    }
  };

  const addFiles = (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (!fileArray.length) {
      return;
    }

    setPhotos(prev => {
      const existingKeys = new Set(prev.map(item => `${item.file.name}-${item.file.lastModified}`));
      const nextItems = fileArray
        .filter(file => file.type.startsWith('image/'))
        .filter(file => !existingKeys.has(`${file.name}-${file.lastModified}`))
        .map(file => ({
          id: generateClientId(),
          file,
          previewUrl: URL.createObjectURL(file),
          captureTime: '',
          locationName: '',
          latitude: '',
          longitude: '',
          status: 'idle' as UploadStatus,
        }));

      return [...prev, ...nextItems];
    });
  };

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      addFiles(event.target.files);
      event.target.value = '';
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!isDragging) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);

    if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
      addFiles(event.dataTransfer.files);
      event.dataTransfer.clearData();
    }
  };

  const handleRemovePhoto = (id: string) => {
    setPhotos(prev => {
      const target = prev.find(item => item.id === id);
      if (target) {
        cleanupPreviewUrl(target.previewUrl);
      }
      return prev.filter(item => item.id !== id);
    });
  };

  const handleClearAll = () => {
    photos.forEach(photo => cleanupPreviewUrl(photo.previewUrl));
    setPhotos([]);
  };

  const updatePhotoField = (
    id: string,
    field: keyof Pick<SelectedPhoto, 'captureTime' | 'locationName' | 'latitude' | 'longitude'>,
    value: string
  ) => {
    setPhotos(prev =>
      prev.map(photo =>
        photo.id === id
          ? {
              ...photo,
              [field]: value,
            }
          : photo
      )
    );
  };

  const applyBulkMetadata = () => {
    setPhotos(prev =>
      prev.map(photo => ({
        ...photo,
        captureTime: bulkCaptureTime || photo.captureTime,
        locationName: bulkLocationName || photo.locationName,
        latitude: bulkLatitude || photo.latitude,
        longitude: bulkLongitude || photo.longitude,
      }))
    );
  };

  const resetResults = () => {
    setPhotos(prev =>
      prev.map(photo => ({
        ...photo,
        status: 'idle',
        error: undefined,
        mediaItemId: undefined,
      }))
    );
  };

  const handleUpload = async () => {
    if (!photos.length) {
      setGlobalError('写真を選択してください');
      return;
    }

    setGlobalError(null);
    setGlobalMessage(null);
    setIsUploading(true);
    setPhotos(prev =>
      prev.map(photo => ({
        ...photo,
        status: 'uploading',
        error: undefined,
      }))
    );

    const requestItems = photos.map(photo => ({
      clientId: photo.id,
      file: photo.file,
      captureTime: toIsoStringOrNull(photo.captureTime),
      locationName: photo.locationName || null,
      latitude: parseCoordinate(photo.latitude),
      longitude: parseCoordinate(photo.longitude),
    }));

    try {
      const formData = createBatchUploadFormData(requestItems);
      const response = await uploadGooglePhotosBatch(formData);
      applyResults(response);
    } catch (error) {
      logger.error('Google Photos batch upload error:', error);
      setGlobalError(error instanceof Error ? error.message : 'アップロードに失敗しました');
      setPhotos(prev =>
        prev.map(photo =>
          photo.status === 'uploading'
            ? { ...photo, status: 'error', error: 'アップロード処理中にエラーが発生しました' }
            : photo
        )
      );
    } finally {
      setIsUploading(false);
    }
  };

  const applyResults = (response: GooglePhotosBatchUploadResponse) => {
    setPhotos(prev =>
      prev.map(photo => {
        const result =
          response.results.find(item => item.clientId === photo.id) ||
          response.results.find(item => item.fileName === photo.file.name);
        if (!result) {
          return {
            ...photo,
            status: 'error',
            error: 'レスポンスから結果を判定できませんでした',
          };
        }
        return {
          ...photo,
          status: result.success ? 'success' : 'error',
          mediaItemId: result.mediaItemId,
          error: result.error ?? undefined,
        };
      })
    );

    if (response.success) {
      setGlobalMessage('すべての写真を Google Photos にアップロードしました');
    } else {
      setGlobalError('一部の写真でエラーが発生しました。各行の詳細をご確認ください');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-4 py-3 sticky top-0 z-40">
        <div className="max-w-6xl mx-auto flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4 mr-1" />
            戻る
          </Button>
          <div>
            <h1 className="text-xl font-semibold text-slate-900">Google Photos 移行ツール</h1>
            <p className="text-sm text-slate-500">大量の写真を選択して日時・位置情報をまとめて登録できます</p>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <UploadCloud className="h-5 w-5 text-blue-600" />
                  写真を追加
                </CardTitle>
                <CardDescription>
                  外付け HDD から選択したファイルをドラッグ＆ドロップ、またはファイル選択ボタンから追加します
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div
                  className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
                    isDragging ? 'border-blue-500 bg-blue-50' : 'border-slate-300'
                  }`}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                >
                  <p className="text-slate-600 mb-4">
                    ここに写真をドロップするか、『写真を選択』ボタンからファイルを追加してください
                  </p>
                  <Button type="button" onClick={() => fileInputRef.current?.click()}>
                    写真を選択
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    multiple
                    className="hidden"
                    onChange={handleFileInputChange}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-lg">選択中の写真</CardTitle>
                  <CardDescription>
                    {photos.length
                      ? `${photos.length} 件中 ${activeCount} 件がアップロード完了`
                      : '写真を追加すると一覧が表示されます'}
                  </CardDescription>
                </div>
                {photos.length > 0 && (
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={resetResults}>
                      ステータスをリセット
                    </Button>
                    <Button variant="outline" size="sm" onClick={handleClearAll}>
                      すべて削除
                    </Button>
                  </div>
                )}
              </CardHeader>
              <CardContent>
                {!photos.length && (
                  <div className="text-center text-slate-500 py-12">
                    まだ写真が選択されていません。ファイルを追加してください。
                  </div>
                )}

                <div className="space-y-6">
                  {photos.map(photo => (
                    <div
                      key={photo.id}
                      className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm"
                    >
                      <div className="flex flex-col md:flex-row gap-4">
                        <img
                          src={photo.previewUrl}
                          alt={photo.file.name}
                          className="w-full md:w-40 h-40 object-cover rounded-lg border border-slate-200"
                        />

                        <div className="flex-1 space-y-4">
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0">
                              <p className="font-semibold text-slate-800 truncate">{photo.file.name}</p>
                              <p className="text-sm text-slate-500">
                                {(photo.file.size / 1024 / 1024).toFixed(2)} MB・
                                {new Date(photo.file.lastModified).toLocaleString()}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              {photo.status === 'success' && (
                                <span className="inline-flex items-center text-green-600 text-sm">
                                  <CheckCircle2 className="h-4 w-4 mr-1" />
                                  完了
                                </span>
                              )}
                              {photo.status === 'error' && (
                                <span className="inline-flex items-center text-red-600 text-sm">
                                  <XCircle className="h-4 w-4 mr-1" />
                                  エラー
                                </span>
                              )}
                              {photo.status === 'uploading' && (
                                <span className="inline-flex items-center text-blue-600 text-sm">
                                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                  アップロード中
                                </span>
                              )}
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => handleRemovePhoto(photo.id)}
                                aria-label="写真を削除"
                                disabled={isUploading}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <Label className="flex items-center gap-2 text-sm text-slate-600">
                                <CalendarClock className="h-4 w-4 text-slate-400" />
                                撮影日時 (JST)
                              </Label>
                              <Input
                                type="datetime-local"
                                value={photo.captureTime}
                                onChange={event => updatePhotoField(photo.id, 'captureTime', event.target.value)}
                                disabled={isUploading}
                              />
                            </div>
                            <div className="space-y-2">
                              <Label className="flex items-center gap-2 text-sm text-slate-600">
                                <MapPin className="h-4 w-4 text-slate-400" />
                                場所のメモ
                              </Label>
                              <Input
                                placeholder="例: 祖父母の家、札幌"
                                value={photo.locationName}
                                onChange={event => updatePhotoField(photo.id, 'locationName', event.target.value)}
                                disabled={isUploading}
                              />
                            </div>
                            <div className="space-y-2">
                              <Label className="text-sm text-slate-600">緯度 (Latitude)</Label>
                              <Input
                                type="text"
                                inputMode="decimal"
                                placeholder="35.6586"
                                value={photo.latitude}
                                onChange={event => updatePhotoField(photo.id, 'latitude', event.target.value)}
                                disabled={isUploading}
                              />
                            </div>
                            <div className="space-y-2">
                              <Label className="text-sm text-slate-600">経度 (Longitude)</Label>
                              <Input
                                type="text"
                                inputMode="decimal"
                                placeholder="139.7454"
                                value={photo.longitude}
                                onChange={event => updatePhotoField(photo.id, 'longitude', event.target.value)}
                                disabled={isUploading}
                              />
                            </div>
                          </div>

                          {photo.error && (
                            <p className="text-sm text-red-600 bg-red-50 rounded-md px-3 py-2">{photo.error}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">一括設定</CardTitle>
                <CardDescription>共通する日時・位置情報をまとめて入力して適用できます</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>撮影日時 (JST)</Label>
                  <Input
                    type="datetime-local"
                    value={bulkCaptureTime}
                    onChange={event => setBulkCaptureTime(event.target.value)}
                    disabled={isUploading}
                  />
                </div>

                <div className="space-y-2">
                  <Label>場所のメモ</Label>
                  <Input
                    placeholder="例: 北海道旅行 2010"
                    value={bulkLocationName}
                    onChange={event => setBulkLocationName(event.target.value)}
                    disabled={isUploading}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>緯度</Label>
                    <Input
                      type="text"
                      inputMode="decimal"
                      value={bulkLatitude}
                      onChange={event => setBulkLatitude(event.target.value)}
                      disabled={isUploading}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>経度</Label>
                    <Input
                      type="text"
                      inputMode="decimal"
                      value={bulkLongitude}
                      onChange={event => setBulkLongitude(event.target.value)}
                      disabled={isUploading}
                    />
                  </div>
                </div>

                <Button
                  type="button"
                  variant="outline"
                  className="w-full"
                  onClick={applyBulkMetadata}
                  disabled={!photos.length || isUploading}
                >
                  すべての写真に適用
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">アップロードの実行</CardTitle>
                <CardDescription>Google Photos に直接送信し、EXIF に日時と GPS 情報を書き込みます</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {globalError && (
                  <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                    <XCircle className="h-4 w-4 mt-0.5" />
                    <span>{globalError}</span>
                  </div>
                )}
                {globalMessage && (
                  <div className="flex items-start gap-2 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
                    <CheckCircle2 className="h-4 w-4 mt-0.5" />
                    <span>{globalMessage}</span>
                  </div>
                )}

                <Button
                  type="button"
                  className="w-full"
                  onClick={handleUpload}
                  disabled={!photos.length || isUploading}
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      アップロード中...
                    </>
                  ) : (
                    'Google Photos にアップロード'
                  )}
                </Button>
                <p className="text-xs text-slate-500">
                  ※ この操作では画像の EXIF に撮影日時と GPS 座標を書き込み、その後 Google Photos API
                  へアップロードします。大容量の写真は通信に時間がかかる場合があります。
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Info className="h-4 w-4 text-blue-500" />
                  運用ヒント
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-slate-600">
                <p>・古い外付け HDD からの移行時に、年月や訪問場所ごとにバッチ処理するのがおすすめです。</p>
                <p>・Google Photos 側でもアルバム {`"`}Coordinate Records{`"`} に自動で整理されます。</p>
                <p>
                  ・位置情報が不明な写真もアップロードできます。未入力の場合は EXIF を変更せずに送信されます。
                </p>
                <p>
                  ・アップロード完了後は安全のためローカルの一時ファイルを削除します。プレビューのために作成した
                  URL は写真を削除すると即時破棄されます。
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
};

export default GooglePhotosBatchUploadPage;
