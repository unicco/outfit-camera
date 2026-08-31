import { useState, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Upload, X, Check, AlertCircle, Loader2, ArrowLeft } from 'lucide-react';
import { DEFAULT_USER_ID } from '@/constants';
import { dateUtils } from '@/utils/dateUtils';
import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';
import { UnifiedAnalysisResult } from '@/components/UnifiedAnalysisResult';
import {
  unifiedAnalysisService,
  type UnifiedAnalysisResponse,
} from '@/services/unifiedAnalysisService';

interface FullBodyPhotoUploadProps {
  apiUrl: string;
  selectedDate?: Date | null;
  onSuccess?: (message: string) => void;
  onBack?: () => void;
}

export function FullBodyPhotoUpload({
  apiUrl,
  selectedDate: propsSelectedDate,
  onSuccess,
  onBack,
}: FullBodyPhotoUploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisResults, setAnalysisResults] = useState<UnifiedAnalysisResponse | null>(null);

  // 選択された日付またはデフォルトの今日の日付（JST）
  const uploadDate = propsSelectedDate || dateUtils.nowJST();
  const dateString = dateUtils.jstToDateString(uploadDate);
  const [message, setMessage] = useState<{
    text: string;
    type: 'success' | 'error';
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const showMessage = (text: string, type: 'success' | 'error' = 'success') => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    const file = files[0];

    if (!file) return;

    // 画像ファイルのみを許可
    if (
      !file.type.startsWith('image/') ||
      !['image/jpeg', 'image/jpg', 'image/png', 'image/webp'].includes(
        file.type
      )
    ) {
      showMessage(
        '対応していないファイル形式です。JPEG、PNG、WebP形式の画像のみアップロード可能です。',
        'error'
      );
      return;
    }

    // 既存のプレビューURLをクリーンアップ
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    setSelectedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
  };

  const removeFile = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setSelectedFile(null);
    setPreviewUrl(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const uploadPhoto = async () => {
    logger.dev('🚀 uploadPhoto function called');

    if (!selectedFile) {
      logger.dev('❌ No file selected');
      showMessage('アップロードする画像を選択してください。', 'error');
      return;
    }

    // propsSelectedDate がない場合は uploadDate（デフォルトは今日）を使用
    const dateToUse = propsSelectedDate || uploadDate;

    if (!dateToUse) {
      logger.dev('❌ No date selected');
      showMessage('日付を選択してください。', 'error');
      return;
    }

    logger.dev('✅ Pre-upload validation passed');
    setUploading(true);
    setAnalysisResults(null);

    // Date オブジェクトを YYYY-MM-DD 形式の文字列に変換（JST基準）
    const dateString =
      dateToUse instanceof Date
        ? dateUtils.jstToDateString(dateToUse)
        : dateToUse;

    logger.dev('Starting upload:', {
      filename: selectedFile.name,
      size: selectedFile.size,
      originalDate: propsSelectedDate,
      convertedDate: dateString,
      uploadUrl: `${apiUrl}/api/v2/upload`,
    });

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('captured_date', dateString);

      // ApiClient の upload メソッドを使用
      interface UploadPhotoResponse {
        id?: string;
        photo_id?: string;
        file_path?: string;
        person_detected?: boolean;
      }
      const result = await apiClient.upload<UploadPhotoResponse>('/api/v2/upload', formData);
      logger.dev('✅ Upload successful:', result);

      // 統合分析を実行
      // uploading を先に落とす。両方 true だとボタンが「分析中...」に切り替わらない
      setUploading(false);
      setAnalyzing(true);
      try {
        const uploadedPhotoId = result.id || result.photo_id || '';
        logger.dev('🔍 Starting unified analysis for photo:', uploadedPhotoId);
        const analysisResult = await unifiedAnalysisService.analyzePhoto({
          photoId: uploadedPhotoId,
          userId: DEFAULT_USER_ID,
          useFewShot: true,
        });

        logger.dev('✅ Analysis complete:', analysisResult);
        setAnalysisResults(analysisResult);

        const formattedDate = dateUtils.formatJSTJapanese(new Date(dateString));
        const message = `${formattedDate}の写真をアップロードし、分析が完了しました`;
        logger.dev('✅ Success message:', message);
        showMessage(message, 'success');

        // 成功時のコールバック
        if (onSuccess) {
          onSuccess(message);
        }
      } catch (analysisError) {
        logger.error('❌ Analysis failed:', analysisError);
        // 分析が失敗してもアップロードは成功しているので続行。
        // 分析エンドポイントは未実装なので**この経路が常に通る**。利用者の操作（保存）は
        // 完了しているため赤の失敗表示にはしない。分析結果は後から一覧側で付く。
        const formattedDate = dateUtils.formatJSTJapanese(new Date(dateString));
        const message = `${formattedDate}の写真をアップロードしました`;
        showMessage(message, 'success');

        // 成功時のコールバック（アップロード自体は成功）
        if (onSuccess) {
          onSuccess(message);
        }
      } finally {
        setAnalyzing(false);
      }

      // ファイル選択をクリア
      removeFile();
    } catch (error) {
      logger.error('Upload error:', error);
      showMessage(
        `アップロード中にエラーが発生しました: ${error instanceof Error ? error.message : 'Unknown error'}`,
        'error'
      );
    } finally {
      setUploading(false);
    }
  };

  const busy = uploading || analyzing;

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      {onBack && (
        <header className="bg-white border-b border-gray-200 px-4 py-3 sticky top-0 z-50">
          <div className="max-w-4xl mx-auto flex items-center">
            <Button variant="ghost" size="sm" onClick={onBack} className="mr-3">
              <ArrowLeft className="h-4 w-4 mr-1" />
              戻る
            </Button>
            <div>
              <h1 className="text-xl font-semibold text-gray-900">
                全身を登録
              </h1>
              <p className="text-sm text-gray-600 mt-1">
                撮影日：{dateUtils.formatJSTJapanese(uploadDate)}
              </p>
            </div>
          </div>
        </header>
      )}

      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* メッセージ */}
        {message && (
          <Alert
            className={`mb-6 ${
              message.type === 'success'
                ? 'bg-green-50 border-green-200 text-green-800'
                : 'bg-red-50 border-red-200 text-red-800'
            }`}
          >
            <AlertDescription className="flex items-center gap-2">
              {message.type === 'success' ? (
                <Check className="h-4 w-4" />
              ) : (
                <AlertCircle className="h-4 w-4" />
              )}
              {message.text}
            </AlertDescription>
          </Alert>
        )}

        {/* Hidden date field */}
        <input type="hidden" value={dateString} name="captured_date" />

        {/* アップロード領域 */}
        <Card className="p-8 mb-8 border-0 shadow-none">
          <div className="text-center">
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 hover:border-gray-400 transition-colors">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/jpg,image/png,image/webp"
                onChange={handleFileSelect}
                className="hidden"
                id="photo-upload"
              />
              <label
                htmlFor="photo-upload"
                className="cursor-pointer flex flex-col items-center gap-4"
              >
                <Upload className="h-12 w-12 text-gray-400" />
                <div>
                  <p className="text-lg font-medium text-gray-900">
                    ファイルを選択またはドラッグ&ドロップ
                  </p>
                  <p className="text-sm text-gray-500 mt-1">
                    JPEG・PNG・WebP 形式
                  </p>
                </div>
              </label>
            </div>
          </div>
        </Card>

        {/* 選択されたファイルのプレビュー */}
        {selectedFile && (
          <Card className="p-6 mb-8 border-0 shadow-none">
            <h3 className="text-lg font-semibold mb-4">選択されたファイル</h3>
            <div className="flex flex-col items-center">
              <div className="relative group max-w-md">
                <div className="aspect-[3/4] bg-gray-100 rounded-lg overflow-hidden">
                  <img
                    src={previewUrl || ''}
                    alt={selectedFile.name}
                    className="w-full h-full object-cover"
                  />
                </div>
                <button
                  onClick={removeFile}
                  className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="h-4 w-4" />
                </button>
                <p className="text-sm text-gray-600 mt-2 text-center">
                  {selectedFile.name}
                </p>
              </div>
              <div className="flex gap-4 mt-6 w-full max-w-md">
                <Button
                  onClick={uploadPhoto}
                  disabled={busy}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
                >
                  {uploading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      アップロード中...
                    </>
                  ) : analyzing ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      分析中...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      アップロード
                    </>
                  )}
                </Button>
                <Button
                  onClick={removeFile}
                  variant="outline"
                  disabled={busy}
                >
                  クリア
                </Button>
              </div>
            </div>
          </Card>
        )}

        {/* 統合分析結果（分析中は同コンポーネントが進捗カードを出す） */}
        {(analyzing || analysisResults) && (
          <div className="mb-8">
            <UnifiedAnalysisResult
              isLoading={analyzing}
              results={analysisResults ?? undefined}
            />
          </div>
        )}

      </div>
    </div>
  );
}
