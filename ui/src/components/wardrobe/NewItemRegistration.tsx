import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { WARDROBE_OCCASIONS } from '@/constants/wardrobe';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Calendar } from '@/components/ui/calendar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { format } from 'date-fns';
import { ja } from 'date-fns/locale';
import {
  Camera,
  Upload,
  Search,
  Plus,
  X,
  CalendarIcon,
  Shirt,
  Tag,
  DollarSign,
  Package,
  Sun,
  CloudRain,
  Snowflake,
  Flower2,
  Trash2,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import {
  getImageUploadService,
  type UploadProgress,
} from '@/services/imageUpload';
import { apiClient } from '@/services/apiClient';
import { logger } from '@/utils/logger';

interface ClothingItemResponse {
  id: string;
  name: string;
  category: string;
  subcategory?: string;
  brand?: string;
  pattern?: string;
  material?: string;
  size?: string;
  purchase_date?: string;
  purchase_price?: number;
  season?: string[];
  occasion?: string[];
  status: string;
  image_urls?: string[];
  tags?: string[];
  created_at: string;
  updated_at: string;
  wear_count?: number;
  last_worn?: string;
  cost_per_wear?: number;
  care_instructions?: string;
  notes?: string;
}

interface NewClothingItem {
  name: string;
  category: string;
  subcategory?: string;
  brand?: string;
  pattern?: string;
  material?: string;
  size?: string;
  purchase_date?: Date;
  purchase_price?: number;
  season: string[];
  occasion: string[];
  care_instructions?: string;
  tags: string[];
  notes?: string;
  image_files?: File[];
  image_urls?: string[];
}

interface NewItemRegistrationProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  apiUrl: string;
  onSuccess: (item: ClothingItemResponse) => void;
  defaultCategory?: string;
  detectedItem?: Partial<NewClothingItem>;
}

const CATEGORIES = [
  { value: 'TOPS', label: 'トップス', icon: Shirt },
  { value: 'BOTTOMS', label: 'ボトムス', icon: Package },
  { value: 'OUTERWEAR', label: 'アウター', icon: Package },
  { value: 'SHOES', label: 'シューズ', icon: Package },
  { value: 'ACCESSORIES', label: 'アクセサリー', icon: Package },
  { value: 'BAG', label: 'バッグ', icon: Package },
];

const SUBCATEGORIES: Record<string, string[]> = {
  TOPS: [
    'Tシャツ',
    'シャツ',
    'ポロシャツ',
    'ニット',
    'スウェット',
    'パーカー',
    'ベスト',
  ],
  BOTTOMS: ['ジーンズ', 'チノパン', 'スラックス', 'ショーツ', 'スカート'],
  OUTERWEAR: ['ジャケット', 'コート', 'ブルゾン', 'ダウン', 'レインコート'],
  SHOES: ['スニーカー', '革靴', 'ブーツ', 'サンダル', 'ローファー'],
  ACCESSORIES: [
    '帽子',
    'ベルト',
    'ネクタイ',
    'マフラー',
    '手袋',
    '時計',
    'メガネ',
  ],
  BAG: ['リュック', 'トートバッグ', 'ショルダーバッグ', 'ブリーフケース'],
};

const PATTERNS = [
  '無地',
  'ストライプ',
  'チェック',
  'ドット',
  '花柄',
  'カモフラージュ',
  'その他',
];

const MATERIALS = [
  'コットン',
  'ウール',
  'ポリエステル',
  'ナイロン',
  'レザー',
  'デニム',
  'リネン',
  'シルク',
  'カシミア',
];

const SEASONS = [
  { value: 'spring', label: '春', icon: Flower2 },
  { value: 'summer', label: '夏', icon: Sun },
  { value: 'autumn', label: '秋', icon: CloudRain },
  { value: 'winter', label: '冬', icon: Snowflake },
];

export function NewItemRegistration({
  open,
  onOpenChange,
  apiUrl,
  onSuccess,
  defaultCategory,
  detectedItem,
}: NewItemRegistrationProps) {
  const [formData, setFormData] = useState<NewClothingItem>({
    name: detectedItem?.name || '',
    category: detectedItem?.category || defaultCategory || '',
    subcategory: detectedItem?.subcategory || '',
    brand: detectedItem?.brand || '',
    pattern: detectedItem?.pattern || '',
    material: detectedItem?.material || '',
    size: detectedItem?.size || '',
    purchase_date: detectedItem?.purchase_date || undefined,
    purchase_price: detectedItem?.purchase_price || undefined,
    season: detectedItem?.season || [],
    occasion: detectedItem?.occasion || [],
    care_instructions: detectedItem?.care_instructions || '',
    tags: detectedItem?.tags || [],
    notes: detectedItem?.notes || '',
    image_files: [],
    image_urls: detectedItem?.image_urls || [],
  });

  const [currentTag, setCurrentTag] = useState('');
  const [uploadedImages, setUploadedImages] = useState<string[]>([]);
  const [registrationMethod, setRegistrationMethod] = useState<
    'camera' | 'upload' | 'search'
  >('camera');
  const [loading, setLoading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState('');

  const handleInputChange = (
    field: keyof NewClothingItem,
    value: string | number | Date | undefined | Record<string, number> | null
  ) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSeasonToggle = (season: string) => {
    setFormData(prev => ({
      ...prev,
      season: prev.season.includes(season)
        ? prev.season.filter(s => s !== season)
        : [...prev.season, season],
    }));
  };

  const handleOccasionToggle = (occasion: string) => {
    setFormData(prev => ({
      ...prev,
      occasion: prev.occasion.includes(occasion)
        ? prev.occasion.filter(o => o !== occasion)
        : [...prev.occasion, occasion],
    }));
  };

  const handleAddTag = () => {
    if (currentTag && !formData.tags.includes(currentTag)) {
      setFormData(prev => ({ ...prev, tags: [...prev.tags, currentTag] }));
      setCurrentTag('');
    }
  };

  const handleRemoveTag = (tag: string) => {
    setFormData(prev => ({ ...prev, tags: prev.tags.filter(t => t !== tag) }));
  };

  const handleImageUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files) {
      const newFiles = Array.from(files);
      setFormData(prev => ({
        ...prev,
        image_files: [...(prev.image_files || []), ...newFiles],
      }));

      // Preview images
      newFiles.forEach(file => {
        const reader = new FileReader();
        reader.onload = e => {
          setUploadedImages(prev => [...prev, e.target?.result as string]);
        };
        reader.readAsDataURL(file);
      });
    }
  };

  const handleSubmit = async () => {
    // Reset error state
    setError('');

    // Validation
    if (!formData.name || !formData.category) {
      setError('必須項目を入力してください');
      return;
    }

    setLoading(true);
    setUploadProgress(0);

    try {
      // Step 1: Create item without images
      setUploadStatus('アイテム情報を登録中...');

      const itemData = {
        name: formData.name,
        category: formData.category,
        subcategory: formData.subcategory || null,
        brand: formData.brand || null,
        pattern: formData.pattern || null,
        material: formData.material || null,
        size: formData.size || null,
        purchase_date: formData.purchase_date
          ? formData.purchase_date.toISOString().split('T')[0]
          : null,
        purchase_price: formData.purchase_price || null,
        care_instructions: formData.care_instructions || null,
        season: formData.season,
        occasion: formData.occasion,
        tags: formData.tags,
        image_urls: [],
      };

      const item = await apiClient.post<ClothingItemResponse>(
        '/wardrobe/items',
        itemData
      );

      // Step 2: Upload images if any
      if (formData.image_files && formData.image_files.length > 0) {
        setUploadStatus('画像をアップロード中...');

        const uploadService = getImageUploadService(apiUrl);

        // Validate files first
        const validation = uploadService.validateFiles(formData.image_files);
        if (!validation.valid) {
          throw new Error(validation.errors.join('\n'));
        }

        try {
          const uploadedImages = await uploadService.uploadItemImages(
            item.id,
            formData.image_files,
            (progress: UploadProgress) => {
              setUploadProgress(progress.percentage);
              setUploadStatus(
                `画像をアップロード中... ${progress.percentage}%`
              );
            }
          );

          // Update item with uploaded image URLs
          item.image_urls = uploadedImages.map(img => img.original_url);
          item.thumbnails = uploadedImages.map(img => img.thumbnails);
        } catch (uploadError) {
          // If image upload fails, the item is still created
          logger.error('Image upload error:', uploadError);

          // Check if it's a timeout error
          const errorMessage = uploadError instanceof Error ? uploadError.message : String(uploadError);
          if (errorMessage.includes('timeout')) {
            // Timeout is not a real error - background processing continues
            logger.info('Upload timeout - background processing continues');
            // タイムアウトも成功として扱う（EditItemPageと統一）
            // アイテムは登録済で、画像処理はバックグラウンドで継続
          } else {
            // Real error
            setError(`画像のアップロードに失敗しました: ${errorMessage}`);
          }
        }
      }

      onSuccess(item);
    } catch (error) {
      logger.error('Error creating item:', error);
      setError(
        error instanceof Error ? error.message : 'アイテムの登録に失敗しました'
      );
    } finally {
      setLoading(false);
      setUploadStatus('');
      setUploadProgress(0);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold">
            ワードローブを追加
          </DialogTitle>
          <DialogDescription>
            ワードローブにアイテムを登録します
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="h-[calc(90vh-200px)] pr-4">
          <div className="space-y-6 pb-6">
            {/* Error Alert */}
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Upload Progress */}
            {uploadStatus && (
              <Card>
                <CardContent className="pt-6">
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span className="text-sm font-medium">
                        {uploadStatus}
                      </span>
                    </div>
                    {uploadProgress > 0 && (
                      <Progress value={uploadProgress} className="w-full" />
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
            {/* Image Registration Method */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">画像の登録方法</CardTitle>
              </CardHeader>
              <CardContent>
                <Tabs
                  value={registrationMethod}
                  onValueChange={v =>
                    setRegistrationMethod(v as 'camera' | 'upload' | 'search')
                  }
                >
                  <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="camera">
                      <Camera className="h-4 w-4 mr-2" />
                      カメラで撮影
                    </TabsTrigger>
                    <TabsTrigger value="upload">
                      <Upload className="h-4 w-4 mr-2" />
                      アップロード
                    </TabsTrigger>
                    <TabsTrigger value="search">
                      <Search className="h-4 w-4 mr-2" />
                      画像検索
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="camera" className="mt-4">
                    <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                      <Camera className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                      <p className="text-gray-600 mb-4">
                        カメラを起動して撮影します
                      </p>
                      <Button>
                        <Camera className="h-4 w-4 mr-2" />
                        カメラを起動
                      </Button>
                    </div>
                  </TabsContent>

                  <TabsContent value="upload" className="mt-4">
                    <div className="space-y-4">
                      <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                        <Upload className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                        <p className="text-gray-600 mb-4">
                          画像をドラッグ＆ドロップまたは選択
                        </p>
                        <Input
                          type="file"
                          accept="image/*"
                          multiple
                          onChange={handleImageUpload}
                          className="hidden"
                          id="image-upload"
                        />
                        <Label
                          htmlFor="image-upload"
                          className="cursor-pointer"
                        >
                          <Button asChild>
                            <span>
                              <Upload className="h-4 w-4 mr-2" />
                              画像を選択
                            </span>
                          </Button>
                        </Label>
                      </div>

                      {uploadedImages.length > 0 && (
                        <div className="grid grid-cols-3 gap-2">
                          {uploadedImages.map((img, index) => (
                            <div
                              key={index}
                              className="relative aspect-square group"
                            >
                              <img
                                src={img}
                                alt={`Upload ${index + 1}`}
                                className="w-full h-full object-cover rounded border-2 border-gray-200"
                              />
                              <Button
                                size="icon"
                                variant="destructive"
                                className="absolute top-1 right-1 h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                                onClick={() => {
                                  setUploadedImages(prev =>
                                    prev.filter((_, i) => i !== index)
                                  );
                                  setFormData(prev => ({
                                    ...prev,
                                    image_files:
                                      prev.image_files?.filter(
                                        (_, i) => i !== index
                                      ) || [],
                                  }));
                                }}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </TabsContent>

                  <TabsContent value="search" className="mt-4">
                    <div className="space-y-4">
                      <div className="flex gap-2">
                        <Input
                          placeholder="商品名やブランドで検索..."
                          className="flex-1"
                        />
                        <Button>
                          <Search className="h-4 w-4 mr-2" />
                          検索
                        </Button>
                      </div>
                      <p className="text-sm text-gray-500">
                        Web上から商品画像を検索して使用します
                      </p>
                    </div>
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>

            {/* Basic Information */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">基本情報</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">アイテム名 *</Label>
                    <Input
                      id="name"
                      placeholder="例: ブルーオックスフォードシャツ"
                      value={formData.name}
                      onChange={e => handleInputChange('name', e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="brand">ブランド</Label>
                    <Input
                      id="brand"
                      placeholder="例: ユニクロ"
                      value={formData.brand}
                      onChange={e => handleInputChange('brand', e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="category">カテゴリー *</Label>
                    <Select
                      value={formData.category}
                      onValueChange={value =>
                        handleInputChange('category', value)
                      }
                    >
                      <SelectTrigger id="category">
                        <SelectValue placeholder="カテゴリーを選択" />
                      </SelectTrigger>
                      <SelectContent>
                        {CATEGORIES.map(cat => (
                          <SelectItem key={cat.value} value={cat.value}>
                            <div className="flex items-center gap-2">
                              <cat.icon className="h-4 w-4" />
                              {cat.label}
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="subcategory">サブカテゴリ</Label>
                    <Select
                      value={formData.subcategory}
                      onValueChange={value =>
                        handleInputChange('subcategory', value)
                      }
                      disabled={!formData.category}
                    >
                      <SelectTrigger id="subcategory">
                        <SelectValue placeholder="サブカテゴリを選択" />
                      </SelectTrigger>
                      <SelectContent>
                        {formData.category &&
                          SUBCATEGORIES[formData.category]?.map(sub => (
                            <SelectItem key={sub} value={sub}>
                              {sub}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-1 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="size">サイズ</Label>
                    <Input
                      id="size"
                      placeholder="例: M, L, 27"
                      value={formData.size}
                      onChange={e => handleInputChange('size', e.target.value)}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="pattern">パターン</Label>
                    <Select
                      value={formData.pattern}
                      onValueChange={value =>
                        handleInputChange('pattern', value)
                      }
                    >
                      <SelectTrigger id="pattern">
                        <SelectValue placeholder="パターンを選択" />
                      </SelectTrigger>
                      <SelectContent>
                        {PATTERNS.map(pattern => (
                          <SelectItem key={pattern} value={pattern}>
                            {pattern}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="material">素材</Label>
                    <Select
                      value={formData.material}
                      onValueChange={value =>
                        handleInputChange('material', value)
                      }
                    >
                      <SelectTrigger id="material">
                        <SelectValue placeholder="素材を選択" />
                      </SelectTrigger>
                      <SelectContent>
                        {MATERIALS.map(material => (
                          <SelectItem key={material} value={material}>
                            {material}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Purchase Information */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">購入情報</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="purchase_date">購入日</Label>
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button
                          variant="outline"
                          className="w-full justify-start text-left font-normal"
                        >
                          <CalendarIcon className="mr-2 h-4 w-4" />
                          {formData.purchase_date
                            ? format(formData.purchase_date, 'yyyy年MM月dd日', {
                                locale: ja,
                              })
                            : '日付を選択'}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0">
                        <Calendar
                          mode="single"
                          selected={formData.purchase_date}
                          onSelect={date =>
                            handleInputChange('purchase_date', date)
                          }
                          initialFocus
                        />
                      </PopoverContent>
                    </Popover>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="purchase_price">購入価格</Label>
                    <div className="relative">
                      <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                      <Input
                        id="purchase_price"
                        type="number"
                        placeholder="0"
                        value={formData.purchase_price || ''}
                        onChange={e =>
                          handleInputChange(
                            'purchase_price',
                            Number(e.target.value)
                          )
                        }
                        className="pl-10"
                      />
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Season & Occasion */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">シーズン・シーン</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label className="mb-3 block">シーズン</Label>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {SEASONS.map(season => (
                      <Button
                        key={season.value}
                        variant={
                          formData.season.includes(season.value)
                            ? 'default'
                            : 'outline'
                        }
                        className="justify-start"
                        onClick={() => handleSeasonToggle(season.value)}
                      >
                        <season.icon className="h-4 w-4 mr-2" />
                        {season.label}
                      </Button>
                    ))}
                  </div>
                </div>

                <div>
                  <Label className="mb-3 block">シーン</Label>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {WARDROBE_OCCASIONS.map(occasion => (
                      <Button
                        key={occasion.value}
                        variant={
                          formData.occasion.includes(occasion.value)
                            ? 'default'
                            : 'outline'
                        }
                        className="justify-start"
                        onClick={() => handleOccasionToggle(occasion.value)}
                      >
                        {occasion.label}
                      </Button>
                    ))}
                  </div>
                </div>

              </CardContent>
            </Card>

            {/* Additional Information */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">追加情報</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="tags">タグ</Label>
                  <div className="flex gap-2">
                    <Input
                      id="tags"
                      placeholder="タグを入力"
                      value={currentTag}
                      onChange={e => setCurrentTag(e.target.value)}
                      onKeyPress={e =>
                        e.key === 'Enter' &&
                        (e.preventDefault(), handleAddTag())
                      }
                    />
                    <Button onClick={handleAddTag} size="icon">
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  {formData.tags.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {formData.tags.map(tag => (
                        <Badge key={tag} variant="secondary" className="gap-1">
                          <Tag className="h-3 w-3" />
                          {tag}
                          <button
                            onClick={() => handleRemoveTag(tag)}
                            className="ml-1 hover:text-red-600"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="care_instructions">お手入れ方法</Label>
                  <Textarea
                    id="care_instructions"
                    placeholder="洗濯方法や保管方法など"
                    value={formData.care_instructions}
                    onChange={e =>
                      handleInputChange('care_instructions', e.target.value)
                    }
                    rows={3}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="notes">メモ</Label>
                  <Textarea
                    id="notes"
                    placeholder="購入理由や着こなしのポイントなど"
                    value={formData.notes}
                    onChange={e => handleInputChange('notes', e.target.value)}
                    rows={3}
                  />
                </div>
              </CardContent>
            </Card>
          </div>
        </ScrollArea>

        <div className="flex justify-end gap-3 pt-4 border-t">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            キャンセル
          </Button>
          <Button
            onClick={handleSubmit}
            className="bg-black text-white hover:bg-gray-800"
            disabled={loading}
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                登録中...
              </>
            ) : (
              '登録する'
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
