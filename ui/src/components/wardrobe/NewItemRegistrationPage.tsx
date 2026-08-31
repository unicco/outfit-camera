import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Upload, X, Plus } from 'lucide-react';
import {
  WARDROBE_CATEGORIES,
  WARDROBE_SEASONS,
  WARDROBE_OCCASIONS,
  WARDROBE_SUBCATEGORIES,
} from '@/constants/wardrobe';
import {
  transformForApiRequest,
} from '@/utils/apiResponseTransformer';
import { apiClient } from '@/services/apiClient';
import { API_ERROR_MESSAGES, API_TIMEOUT } from '@/config/api';
import { logger } from '@/utils/logger';

interface NewItemRegistrationPageProps {
  apiUrl: string;
  onClose: () => void;
  onSuccess?: () => void;
  onShowMessage?: (message: string, type?: 'success' | 'error') => void;
}

// Constants imported from centralized location

export function NewItemRegistrationPage({
  onClose,
  onSuccess,
  onShowMessage,
}: NewItemRegistrationPageProps) {
  const [loading, setLoading] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    category: '',
    subcategory: '',
    brand: '',
    size: '',
    purchase_date: '',
    purchase_price: '',
    purchase_location: '',
    selectedSeasons: [] as string[],
    selectedOccasions: [] as string[],
    tags: [] as string[],
    notes: '',
  });
  const [newTag, setNewTag] = useState('');

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSeasonToggle = (season: string) => {
    setFormData(prev => ({
      ...prev,
      selectedSeasons: prev.selectedSeasons.includes(season)
        ? prev.selectedSeasons.filter(s => s !== season)
        : [...prev.selectedSeasons, season],
    }));
  };

  const handleOccasionToggle = (occasion: string) => {
    setFormData(prev => ({
      ...prev,
      selectedOccasions: prev.selectedOccasions.includes(occasion)
        ? prev.selectedOccasions.filter(o => o !== occasion)
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
      tags: prev.tags.filter(t => t !== tag),
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      // Step 1: Create the item with JSON
      const itemData = {
        name: formData.category, // Use category as name since we don't have a name field
        category: formData.category, // カテゴリは小文字で保存し、表示時に日本語化
        subcategory: formData.subcategory || null,
        brand: formData.brand || null,
        size: formData.size || null,
        purchaseDate: formData.purchase_date || null,
        purchasePrice: formData.purchase_price
          ? parseFloat(formData.purchase_price)
          : null,
        season:
          formData.selectedSeasons.length > 0 ? formData.selectedSeasons : null,
        occasion:
          formData.selectedOccasions.length > 0
            ? formData.selectedOccasions
            : null,
        tags: formData.tags.length > 0 ? formData.tags : null,
        careInstructions: formData.notes || null,
      };

      // Use ApiClient instead of fetch
      const createdItem = await apiClient.post('/api/v2/wardrobe/items', transformForApiRequest(itemData));

      // Step 2: Upload image if available
      const imageInput = document.getElementById('image') as HTMLInputElement;
      if (imageInput?.files?.[0] && createdItem.id) {
        const formData = new FormData();
        formData.append('files', imageInput.files[0]);

        try {
          await apiClient.post(`/api/v2/wardrobe/items/${createdItem.id}/images`, formData, {
            skipTransform: true, // FormData should not be transformed
            timeout: API_TIMEOUT.FILE_UPLOAD,
          });
        } catch (imageError) {
          logger.error('Failed to upload image:', imageError);
          // Continue with success since item was created successfully
        }
      }

      onShowMessage?.('服を追加しました', 'success');
      onSuccess?.();
    } catch (error) {
      logger.error('Error creating item:', error);
      // Use API_ERROR_MESSAGES for consistent error messaging
      const errorMessage = error instanceof Error && error.message in API_ERROR_MESSAGES
        ? API_ERROR_MESSAGES[error.message as keyof typeof API_ERROR_MESSAGES]
        : API_ERROR_MESSAGES.GENERIC;
      onShowMessage?.(errorMessage, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      {onClose && (
        <header className="bg-white border-b border-gray-200 px-4 py-3 sticky top-0 z-50">
          <div className="max-w-2xl mx-auto flex items-center">
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="mr-3"
            >
              <ArrowLeft className="h-4 w-4 mr-1" />
              戻る
            </Button>
            <h1 className="text-xl font-semibold text-gray-900">
              ワードローブを登録
            </h1>
          </div>
        </header>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="p-4 space-y-6 max-w-2xl mx-auto">
        {/* Image Upload */}
        <div className="space-y-2">
          <Label htmlFor="image">写真 *</Label>
          <div className="relative">
            <input
              type="file"
              id="image"
              accept="image/*"
              onChange={handleImageChange}
              className="hidden"
              required
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
              <SelectTrigger>
                <SelectValue placeholder="カテゴリを選択" />
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
                <SelectValue placeholder="サブカテゴリを選択" />
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
            <Label htmlFor="purchase_date">購入日</Label>
            <Input
              type="date"
              id="purchase_date"
              value={formData.purchase_date}
              onChange={e =>
                setFormData(prev => ({
                  ...prev,
                  purchase_date: e.target.value,
                }))
              }
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="purchase_price">購入価格</Label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                ¥
              </span>
              <Input
                type="number"
                id="purchase_price"
                value={formData.purchase_price}
                onChange={e =>
                  setFormData(prev => ({
                    ...prev,
                    purchase_price: e.target.value,
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
              placeholder="例: ZOZOTOWN"
            />
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
                value={newTag}
                onChange={e => setNewTag(e.target.value)}
                placeholder="タグを追加"
                onKeyPress={e =>
                  e.key === 'Enter' && (e.preventDefault(), handleAddTag())
                }
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
                {formData.tags.map(tag => (
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

        {/* Submit Button */}
        <div className="sticky bottom-0 -mx-4 -mb-4">
          <button
            type="submit"
            disabled={
              loading ||
              !formData.category ||
              !imagePreview
            }
            className="w-full bg-blue-600 text-white hover:bg-blue-700 transition-colors py-5 text-xl font-medium disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed"
          >
            {loading ? '登録中...' : '登録'}
          </button>
        </div>
      </form>
    </div>
  );
}
