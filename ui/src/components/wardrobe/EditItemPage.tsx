import { useState } from 'react';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import {
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Badge,
} from '@/components/ui';
import { ArrowLeft, Upload, X, Plus } from 'lucide-react';
import { getBestImageUrl } from '@/utils/imageUtils';
import {
  WARDROBE_CATEGORIES,
  WARDROBE_SEASONS,
  WARDROBE_OCCASIONS,
  WARDROBE_SUBCATEGORIES,
  WARDROBE_STATUSES,
  SALE_PLATFORMS,
  getStatusLabel,
} from '@/constants/wardrobe';
import { apiClient } from '@/services/apiClient';
import { API_TIMEOUT } from '@/config/api';
import { logger } from '@/utils/logger';
// Constants imported from centralized location

interface EditItemPageProps {
  item: ExtendedClothingItem;
  apiUrl: string;
  onClose: () => void;
  onSuccess?: () => void;
  onShowMessage?: (message: string, type?: 'success' | 'error') => void;
}

const EditItemPage: React.FC<EditItemPageProps> = ({
  item,
  apiUrl,
  onClose,
  onSuccess,
  onShowMessage,
}) => {
  const [loading, setLoading] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(
    getBestImageUrl(item.imageUrls, apiUrl, false) || null
  );
  const [formData, setFormData] = useState({
    category: item.category || '',
    subcategory: item.subcategory || '',
    brand: item.brand || '',
    size: item.size || '',
    purchaseDate: item.purchaseDate || '',
    disposalDate: item.disposalDate || '',
    salePlatform: item.salePlatform || '',
    salePrice:
      item.salePrice !== undefined && item.salePrice !== null
        ? item.salePrice.toString()
        : '',
    saleCommission:
      item.saleCommission !== undefined && item.saleCommission !== null
        ? item.saleCommission.toString()
        : '',
    purchasePrice: item.purchasePrice?.toString() || '',
    purchase_location: item.purchaseLocation || '',
    selectedSeasons: item.season || [],
    selectedOccasions: item.occasion || [],
    tags: item.tags || [],
    notes: item.notes || item.careInstructions || '',
    status: item.status || 'ACTIVE',
    lastUsedDate: item.lastWorn || item.lastUsedDate || '',
    defaultUsageCount: item.defaultUsageCount?.toString() || '0',
  });
  const [newTag, setNewTag] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{
    isUploading: boolean;
    message: string;
  }>({ isUploading: false, message: '' });


  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const uploadImage = async () => {
    if (!selectedFile) return;

    try {
      setUploadProgress({
        isUploading: true,
        message: '画像をアップロード中...',
      });

      const formData = new FormData();
      formData.append('files', selectedFile);

      const normalizedId = normalizeUUID(item.id);

      // 5 秒後に AI 処理開始メッセージを表示
      const aiProcessTimeout = setTimeout(() => {
        setUploadProgress({
          isUploading: true,
          message: 'AI による画像分析中……',
        });
      }, 5000);

      try {
        await apiClient.post(`/api/v2/wardrobe/items/${normalizedId}/images`, formData, {
          timeout: API_TIMEOUT.FILE_UPLOAD,
        });
        clearTimeout(aiProcessTimeout);
        setUploadProgress({ isUploading: false, message: '' });
        onShowMessage?.('画像をアップロードしました', 'success');
        setSelectedFile(null);
        return true;
      } catch (apiError) {
        clearTimeout(aiProcessTimeout);
        setUploadProgress({ isUploading: false, message: '' });
        const errorMessage = apiError instanceof Error ? apiError.message : '不明なエラー';
        throw Object.assign(new Error(`画像アップロード失敗: ${errorMessage}`), {
          cause: apiError,
        });
      }
    } catch (error) {
      setUploadProgress({ isUploading: false, message: '' });
      logger.error('Image upload error:', error);

      if (error instanceof Error && error.name === 'AbortError') {
        onShowMessage?.('✅ 画像をアップロードしました！AI 分析はバックグラウンドで処理中です', 'success');
        return true; // Consider it a success
      } else {
        const errorMessage = error instanceof Error ? error.message : String(error);
        onShowMessage?.(`画像アップロード失敗: ${errorMessage}`, 'error');
      }
      return false;
    }
  };

  const handleSeasonToggle = (season: string) => {
    setFormData(prev => ({
      ...prev,
      selectedSeasons: prev.selectedSeasons.includes(season)
        ? prev.selectedSeasons.filter((s: string) => s !== season)
        : [...prev.selectedSeasons, season],
    }));
  };

  const handleOccasionToggle = (occasion: string) => {
    setFormData(prev => ({
      ...prev,
      selectedOccasions: prev.selectedOccasions.includes(occasion)
        ? prev.selectedOccasions.filter((o: string) => o !== occasion)
        : [...prev.selectedOccasions, occasion],
    }));
  };

  const handleAddTag = () => {
    if (newTag.trim() && !formData.tags.includes(newTag.trim())) {
      setFormData(prev => ({
        ...prev,
        tags: [...prev.tags, newTag.trim()],
      }));
      setNewTag('');
    }
  };

  const handleInputChange = (
    field: string,
    value: string | Record<string, unknown>
  ) => {
    setFormData(prev => {
      const newData = { ...prev, [field]: value };
      // Reset subcategory when category changes
      if (field === 'category') {
        newData.subcategory = '';
      }
      return newData;
    });
  };

  const handleRemoveTag = (tag: string) => {
    setFormData(prev => ({
      ...prev,
      tags: prev.tags.filter((t: string) => t !== tag),
    }));
  };

  const normalizeUUID = (uuid: string): string => {
    // Remove hyphens and add them back in standard UUID format
    const cleaned = uuid.replace(/-/g, '');
    if (cleaned.length !== 32) return uuid; // Return original if not valid length
    return `${cleaned.slice(0, 8)}-${cleaned.slice(8, 12)}-${cleaned.slice(12, 16)}-${cleaned.slice(16, 20)}-${cleaned.slice(20)}`;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const normalizedId = normalizeUUID(item.id);
      await apiClient.put(
        `/api/v2/wardrobe/items/${normalizedId}`,
        {
          name: formData.category, // Use category as name since we don't have a name field
          category: formData.category.toUpperCase(), // カテゴリは大文字で保存（PR #953）
          subcategory: formData.subcategory || null,
          brand: formData.brand || null,
          size: formData.size || null,
          purchaseDate: formData.purchaseDate || null,
          disposalDate: formData.disposalDate || null,
          salePlatform: formData.salePlatform || null,
          salePrice: formData.salePrice
            ? parseFloat(formData.salePrice)
            : null,
          saleCommission: formData.saleCommission
            ? parseFloat(formData.saleCommission)
            : null,
          purchasePrice: formData.purchasePrice
            ? parseFloat(formData.purchasePrice)
            : null,
          purchaseLocation: formData.purchase_location || null,
          season:
            formData.selectedSeasons.length > 0
              ? formData.selectedSeasons
              : null,
          occasion:
            formData.selectedOccasions.length > 0
              ? formData.selectedOccasions
              : null,
          tags: formData.tags.length > 0 ? formData.tags : null,
          careInstructions: formData.notes || null,
          status: formData.status.toUpperCase(),
          lastUsedDate: formData.lastUsedDate || null,
          defaultUsageCount: formData.defaultUsageCount
            ? parseInt(formData.defaultUsageCount, 10)
            : null,
        }
      );

      // 画像がある場合はアップロードも実行
      if (selectedFile) {
        await uploadImage();
      }

      // 売却情報・処分日・ステータスはすべて上のメイン PUT で更新する。
      // 以前あった別 API（/sale-info）への 2 本目の呼び出しは、
      // 処分情報から status を自動 DISPOSED に上書きしてアクティブ復帰を打ち消すため廃止。

      onShowMessage?.('服を更新しました', 'success');
      onSuccess?.();
      // onClose()は削除 - onSuccessが適切な画面遷移を処理する
    } catch (error) {
      logger.error('Error updating item:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white border-b border-gray-200">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-4">
            <button
              onClick={onClose}
              className="hover:bg-gray-100 h-12 w-12 flex items-center justify-center rounded-lg transition-colors"
            >
              <ArrowLeft className="h-7 w-7" />
            </button>
            <h1 className="text-lg font-bold">服を編集</h1>
          </div>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="p-4 space-y-6 max-w-2xl mx-auto">
        {/* Image Upload */}
        <div className="space-y-2">
          <Label htmlFor="image">写真</Label>
          <div className="relative">
            <input
              type="file"
              id="image"
              accept="image/*"
              onChange={handleImageChange}
              className="hidden"
            />
            <label
              htmlFor="image"
              className="block w-full aspect-square bg-gray-100 rounded-lg border-2 border-dashed border-gray-300 hover:border-gray-400 cursor-pointer transition-colors"
            >
              {imagePreview ? (
                <img
                  src={imagePreview}
                  alt="Preview"
                  className="w-full h-full object-cover rounded-lg"
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-gray-500">
                  <Upload className="h-12 w-12 mb-2" />
                  <span className="text-sm">写真をアップロード</span>
                </div>
              )}
            </label>
            {selectedFile && (
              <div className="mt-2 space-y-2">
                <Button
                  type="button"
                  onClick={uploadImage}
                  disabled={loading || uploadProgress.isUploading}
                  className="w-full"
                  variant="outline"
                >
                  {uploadProgress.isUploading ? 'アップロード中…' : '画像をアップロード'}
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Basic Info */}
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="category">カテゴリ *</Label>
            <Select
              value={formData.category}
              onValueChange={value => handleInputChange('category', value)}
              required
            >
              <SelectTrigger id="category">
                <SelectValue placeholder="カテゴリを選択">
                  {formData.category
                    ? WARDROBE_CATEGORIES.find(
                        cat => cat.value === formData.category
                      )?.label
                    : 'カテゴリを選択'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {WARDROBE_CATEGORIES.map(cat => (
                  <SelectItem key={cat.value} value={cat.value}>
                    {cat.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="subcategory">サブカテゴリ</Label>
            <Select
              value={formData.subcategory}
              onValueChange={value => handleInputChange('subcategory', value)}
              disabled={!formData.category}
            >
              <SelectTrigger id="subcategory">
                <SelectValue placeholder="サブカテゴリを選択">
                  {formData.subcategory || 'サブカテゴリを選択'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {formData.category &&
                  WARDROBE_SUBCATEGORIES[formData.category]?.map(sub => (
                    <SelectItem key={sub} value={sub}>
                      {sub}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>


          <div className="space-y-2">
            <Label htmlFor="brand">ブランド</Label>
            <Input
              id="brand"
              value={formData.brand}
              onChange={e =>
                setFormData(prev => ({ ...prev, brand: e.target.value }))
              }
              placeholder="例: UNIQLO"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="size">サイズ</Label>
            <Input
              id="size"
              value={formData.size}
              onChange={e =>
                setFormData(prev => ({ ...prev, size: e.target.value }))
              }
              placeholder="例: M, L, 26.5cm"
            />
          </div>
        </div>

        {/* Purchase Info */}
        <div className="space-y-4 pt-4">
          <h3 className="font-semibold">購入情報</h3>

          <div className="space-y-2">
            <Label htmlFor="purchaseDate">購入日</Label>
            <Input
              type="date"
              id="purchaseDate"
              value={formData.purchaseDate}
              onChange={e =>
                setFormData(prev => ({
                  ...prev,
                  purchaseDate: e.target.value,
                }))
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="disposalDate">処分日</Label>
            <Input
              type="date"
              id="disposalDate"
              value={formData.disposalDate}
              onChange={e =>
                setFormData(prev => ({
                  ...prev,
                  disposalDate: e.target.value,
                }))
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="purchasePrice">購入価格</Label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                ¥
              </span>
              <Input
                type="number"
                id="purchasePrice"
                value={formData.purchasePrice}
                onChange={e =>
                  setFormData(prev => ({
                    ...prev,
                    purchasePrice: e.target.value,
                  }))
                }
                placeholder="0"
                className="pl-8"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="purchase_location">購入場所</Label>
            <Input
              id="purchase_location"
              value={formData.purchase_location}
              onChange={e =>
                setFormData(prev => ({
                  ...prev,
                  purchase_location: e.target.value,
                }))
              }
              placeholder="例: UNIQLO, 楽天市場, Amazon"
            />
          </div>
        </div>

        {/* Sale / Disposal Info */}
        <div className="space-y-4 pt-4">
          <h3 className="font-semibold">処分情報</h3>

          <div className="space-y-2">
            <Label htmlFor="salePlatform">売却先</Label>
            <Select
              value={formData.salePlatform}
              onValueChange={value => handleInputChange('salePlatform', value)}
            >
              <SelectTrigger id="salePlatform">
                <SelectValue placeholder="売却先を選択">
                  {formData.salePlatform
                    ? SALE_PLATFORMS.find(
                        platform => platform.value === formData.salePlatform
                      )?.label
                    : '売却先を選択'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {SALE_PLATFORMS.map(platform => (
                  <SelectItem key={platform.value} value={platform.value}>
                    {platform.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="salePrice">売却価格</Label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                ¥
              </span>
              <Input
                type="number"
                id="salePrice"
                value={formData.salePrice}
                onChange={e =>
                  setFormData(prev => ({
                    ...prev,
                    salePrice: e.target.value,
                  }))
                }
                placeholder="0"
                className="pl-8"
                min="0"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="saleCommission">手数料</Label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                ¥
              </span>
              <Input
                type="number"
                id="saleCommission"
                value={formData.saleCommission}
                onChange={e =>
                  setFormData(prev => ({
                    ...prev,
                    saleCommission: e.target.value,
                  }))
                }
                placeholder="0"
                className="pl-8"
                min="0"
              />
            </div>
          </div>
        </div>

        {/* Season */}
        <div className="space-y-4 pt-4">
          <h3 className="font-semibold">シーズン</h3>
          <div className="flex flex-wrap gap-2">
            {WARDROBE_SEASONS.map(season => (
              <Button
                key={season.value}
                type="button"
                variant={
                  formData.selectedSeasons.includes(season.value)
                    ? 'default'
                    : 'outline'
                }
                size="sm"
                onClick={() => handleSeasonToggle(season.value)}
              >
                {season.label}
              </Button>
            ))}
          </div>
        </div>

        {/* Occasion（専用・特別な場の TPO。日常の重複シーンは下のタグへ） */}
        <div className="space-y-4 pt-4">
          <h3 className="font-semibold">シーン（TPO）</h3>
          <div className="flex flex-wrap gap-2">
            {WARDROBE_OCCASIONS.map(occasion => (
              <Button
                key={occasion.value}
                type="button"
                variant={
                  formData.selectedOccasions.includes(occasion.value)
                    ? 'default'
                    : 'outline'
                }
                size="sm"
                onClick={() => handleOccasionToggle(occasion.value)}
              >
                {occasion.label}
              </Button>
            ))}
          </div>
        </div>

        {/* Tags */}
        <div className="space-y-4 pt-4">
          <h3 className="font-semibold">タグ</h3>
          <div className="space-y-2">
            <div className="flex gap-2">
              <Input
                id="newTag"
                value={newTag}
                onChange={e => setNewTag(e.target.value)}
                placeholder="タグを追加"
                onKeyPress={e =>
                  e.key === 'Enter' && (e.preventDefault(), handleAddTag())
                }
                aria-label="新しいタグを追加"
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={handleAddTag}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            {formData.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {formData.tags.map((tag: string) => (
                  <Badge key={tag} variant="secondary" className="gap-1">
                    {tag}
                    <button
                      type="button"
                      onClick={() => handleRemoveTag(tag)}
                      className="ml-1 hover:text-gray-700"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Status */}
        <div className="space-y-2 pt-4">
          <Label htmlFor="status">ステータス</Label>
          <Select
            value={formData.status}
            onValueChange={value => handleInputChange('status', value)}
          >
            <SelectTrigger id="status">
              <SelectValue placeholder="ステータスを選択">
                {formData.status
                  ? getStatusLabel(formData.status.toUpperCase())
                  : 'ステータスを選択'}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {WARDROBE_STATUSES.map(status => (
                <SelectItem
                  key={status.value}
                  value={status.value}
                >
                  {status.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Wear History */}
        <div className="space-y-4 pt-4">
          <h3 className="font-semibold">着用履歴</h3>

          <div className="space-y-2">
            <Label htmlFor="lastUsedDate">最終着用日</Label>
            <Input
              type="date"
              id="lastUsedDate"
              value={formData.lastUsedDate}
              onChange={e =>
                setFormData(prev => ({
                  ...prev,
                  lastUsedDate: e.target.value,
                }))
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="defaultUsageCount">初期着用回数</Label>
            <Input
              type="number"
              id="defaultUsageCount"
              value={formData.defaultUsageCount}
              onChange={e =>
                setFormData(prev => ({
                  ...prev,
                  defaultUsageCount: e.target.value,
                }))
              }
              placeholder="0"
              min="0"
            />
            <p className="text-xs text-gray-500">
              システム登録前の着用回数（購入してからシステムに登録するまでの着用回数）
            </p>
          </div>

          <div className="p-3 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-700">
              <span className="font-medium">総着用回数: </span>
              {item.wearCount.toLocaleString()} 回
            </p>
            <p className="text-xs text-gray-500 mt-1">
              （初期着用回数 {(item.defaultUsageCount || 0).toLocaleString()} 回 + システム記録回数 {(item.usageCount || 0).toLocaleString()} 回）
            </p>
          </div>
        </div>

        {/* Notes */}
        <div className="space-y-2 pt-4">
          <Label htmlFor="notes">メモ</Label>
          <textarea
            id="notes"
            value={formData.notes}
            onChange={e =>
              setFormData(prev => ({ ...prev, notes: e.target.value }))
            }
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Action Buttons */}
        <div className="sticky bottom-0 -mx-4 -mb-4 space-y-2">
          {/* Update Button */}
          <button
            type="submit"
            disabled={loading || !formData.category}
            className="w-full bg-blue-600 text-white hover:bg-blue-700 transition-colors py-5 text-xl font-medium disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed"
          >
            {loading ? '更新中…' : '更新'}
          </button>
        </div>
      </form>
    </div>
  );
};

export { EditItemPage };
