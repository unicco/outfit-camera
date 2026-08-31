import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Calendar,
  DollarSign,
  Tag,
  Package,
  TrendingUp,
  // Clock,
  ArrowLeft,
  Sun,
  CloudRain,
  Snowflake,
  Flower2,
  Edit,
  MapPin,
  Palette,
} from 'lucide-react';
import type { ExtendedClothingItem } from '@/types/wardrobe';
import { getBestImageUrl } from '@/utils/imageUtils';
import { formatNumber } from '@/utils/numberUtils';
import {
  getCategorySubcategoryDisplay,
  getCategoryLabel,
} from '@/constants/wardrobe';
import { SaleInfoDisplay } from './SaleInfoDisplay';

interface ClothingItemDetailProps {
  item: ExtendedClothingItem | null;
  onClose: () => void;
  apiUrl: string;
  onEdit?: () => void;
}

const seasonIcons = {
  spring: { icon: Flower2, label: '春' },
  summer: { icon: Sun, label: '夏' },
  autumn: { icon: CloudRain, label: '秋' },
  winter: { icon: Snowflake, label: '冬' },
};

export function ClothingItemDetail({
  item,
  onClose,
  apiUrl,
  onEdit,
}: ClothingItemDetailProps) {

  if (!item) return null;

  const translateStatus = (status: string) => {
    const statusMap: { [key: string]: string } = {
      ACTIVE: 'アクティブ',
      DISPOSAL_CONSIDERATION: '処分検討中',
      SELLING: '出品中',
      DISPOSED: '処分済',
      // Legacy status mappings for compatibility
      active: 'アクティブ',
      stored: '保管中',
      sold: '売却済',
      sell_candidate: '売却検討',
      retired: '処分済',
    };
    return statusMap[status] || status;
  };

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white border-b border-gray-200">
        <div className="flex items-center gap-4 p-4">
          <button
            onClick={onClose}
            className="hover:bg-gray-100 h-12 w-12 flex items-center justify-center rounded-lg transition-colors"
          >
            <ArrowLeft className="h-7 w-7" />
          </button>
          <div className="flex-1">
            <h1 className="text-lg font-bold">
              {getCategoryLabel(item.category)}
            </h1>
            <p className="text-sm text-gray-600">
              {item.brand || 'ノーブランド'}
            </p>
          </div>
          <button
            className="hover:bg-gray-100 h-12 w-12 flex items-center justify-center rounded-lg transition-colors"
            onClick={onEdit}
          >
            <Edit className="h-7 w-7" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 space-y-6">
        {/* Image - smaller on mobile */}
        <div className="relative w-full max-w-xs mx-auto aspect-square bg-gray-100 rounded-lg overflow-hidden">
          {(() => {
            const imageUrl = getBestImageUrl(item.imageUrls, apiUrl, false);

            if (!imageUrl) {
              return (
                <div className="w-full h-full flex items-center justify-center text-gray-400">
                  <Package className="h-16 w-16" />
                </div>
              );
            }

            return (
              <img
                src={imageUrl}
                alt={item.category}
                className="w-full h-full object-cover"
                onError={e => {
                  // Fallback to original URL if thumbnail fails
                  const originalUrl = getBestImageUrl(
                    item.imageUrls,
                    apiUrl,
                    false
                  );
                  if (originalUrl && originalUrl !== imageUrl) {
                    e.currentTarget.src = originalUrl;
                  }
                }}
              />
            );
          })()}
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-2 -mx-4">
          <div className="border-t border-r border-b border-gray-200 p-4">
            <div className="flex items-center gap-2 text-gray-600 mb-1">
              <DollarSign className="h-4 w-4" />
              <span className="text-sm">コスパ</span>
            </div>
            <p className="text-2xl font-bold">
              <span className="text-lg">¥</span>
              {item.costPerWear !== undefined && item.costPerWear !== null
                ? formatNumber(Math.round(item.costPerWear))
                : '0'}
            </p>
            <p className="text-xs text-gray-500">1 回あたり</p>
          </div>

          <div className="border-t border-b border-gray-200 p-4">
            <div className="flex items-center gap-2 text-gray-600 mb-1">
              <TrendingUp className="h-4 w-4" />
              <span className="text-sm">着用回数</span>
            </div>
            <p className="text-2xl font-bold">
              {formatNumber(item.wearCount || 0)}{' '}
              <span className="text-lg">回</span>
            </p>
            <p className="text-xs text-gray-500">
              {item.lastWorn
                ? `${new Date(item.lastWorn).toLocaleDateString('ja-JP')}`
                : '未着用'}
            </p>
          </div>
        </div>

        {/* Details */}
        <div className="-mx-4">
          <div className="">
            <div className="px-4 pb-4 space-y-3">
              <h3 className="font-semibold flex items-center gap-2">
                <Tag className="h-4 w-4" />
                基本情報
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">カテゴリ</span>
                  <span className="font-medium">
                    {getCategorySubcategoryDisplay(
                      item.category,
                      item.subcategory
                    )}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">ブランド</span>
                  <span className="font-medium">
                    {item.brand || 'ノーブランド'}
                  </span>
                </div>
                {(item.season && item.season.length > 0) ||
                (item.occasion && item.occasion.length > 0) ||
                (item.tags && item.tags.length > 0) ? (
                  <div className="pt-2 border-t border-gray-100">
                    <div className="flex flex-wrap gap-2">
                      {item.season &&
                        item.season.length > 0 &&
                        item.season.map(season => {
                          const SeasonIcon =
                            seasonIcons[season as keyof typeof seasonIcons]
                              ?.icon || Sun;
                          const label =
                            seasonIcons[season as keyof typeof seasonIcons]
                              ?.label || season;
                          return (
                            <Badge key={season} variant="secondary">
                              <SeasonIcon className="h-3 w-3 mr-1" />
                              {label}
                            </Badge>
                          );
                        })}
                      {item.occasion &&
                        item.occasion.length > 0 &&
                        item.occasion.map(occasion => (
                          <Badge key={occasion} variant="default">
                            {occasion}
                          </Badge>
                        ))}
                      {item.tags &&
                        item.tags.length > 0 &&
                        item.tags.map(tag => (
                          <Badge key={tag} variant="outline">
                            {tag}
                          </Badge>
                        ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          {/* Purchase Information Section */}
          <div className="p-4 space-y-3">
            <h3 className="font-semibold flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              購入情報
            </h3>
            <div className="space-y-2 text-sm">
              {item.purchaseDate && (
                <div className="flex justify-between">
                  <span className="text-gray-600">購入日</span>
                  <span className="font-medium">
                    {new Date(item.purchaseDate).toLocaleDateString('ja-JP')}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-600">場所</span>
                <span className="font-medium flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  {item.purchaseLocation || 'オンライン'}
                </span>
              </div>
              {item.purchasePrice && (
                <div className="flex justify-between">
                  <span className="text-gray-600">金額</span>
                  <span className="font-medium">
                    ¥{item.purchasePrice.toLocaleString()}
                  </span>
                </div>
              )}
              {item.disposalDate && (
                <div className="flex justify-between">
                  <span className="text-gray-600">処分日</span>
                  <span className="font-medium">
                    {new Date(item.disposalDate).toLocaleDateString('ja-JP')}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Sale Information Section - show for disposed items */}
          {item.status === 'DISPOSED' && (
            <div className="p-4 space-y-3">
              <SaleInfoDisplay item={item} />
            </div>
          )}

          {/* AI Analysis Section */}
          <div className="p-4 space-y-4">
            <h3 className="font-semibold flex items-center gap-2">
              <Palette className="h-4 w-4" />
              AI 分析
            </h3>

            <Card>
              <CardHeader className="p-3 pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Palette className="h-4 w-4" />
                  Jina Embedding 情報
                </CardTitle>
              </CardHeader>
              <CardContent className="p-3 pt-0 space-y-2">
                <div className="text-xs space-y-1">
                  <div className="flex justify-between">
                    <span className="text-gray-500">モデル:</span>
                    <span className="font-mono text-xs">
                      {item.embeddingModelVersion || 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">計算日時:</span>
                    <span className="text-xs">
                      {item.embeddingComputedAt
                        ? new Date(item.embeddingComputedAt).toLocaleString(
                            'ja-JP'
                          )
                        : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">ベクトル次元:</span>
                    <span className="font-mono text-xs">
                      {item.embeddingVector?.length || 'N/A'}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>


            {/* Color Distribution Card */}
            {item.colorDistribution && (
              <Card>
                <CardHeader className="p-3 pb-2">
                  <CardTitle className="text-sm font-medium">
                    色分布データ
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-3 pt-0">
                  <div className="text-xs font-mono bg-gray-50 p-2 rounded max-h-16 overflow-y-auto">
                    {JSON.stringify(item.colorDistribution, null, 2)}
                  </div>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader className="p-3 pb-2">
                <CardTitle className="text-sm font-medium">
                  AI 分析データ
                </CardTitle>
              </CardHeader>
              <CardContent className="p-3 pt-0">
                <div className="text-xs font-mono bg-gray-50 p-2 rounded max-h-32 overflow-y-auto whitespace-pre-wrap">
                  {JSON.stringify(
                    {
                      id: item.id,
                      name: item.name,
                      category: item.category,
                      subcategory: item.subcategory,
                      colorDistribution: item.colorDistribution,
                      imageMetadata: item.imageMetadata,
                      embeddingVectorPreview: item.embeddingVector
                        ? `[${item.embeddingVector.slice(0, 5).join(', ')}...] (${item.embeddingVector.length} dims)`
                        : 'N/A',
                      tags: item.tags,
                      material: item.material,
                      pattern: item.pattern,
                      brand: item.brand,
                      status: item.status,
                    },
                    null,
                    2
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="">
            <div className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">ステータス</span>
                <Badge
                  variant={item.status === 'ACTIVE' || item.status === 'active' ? 'default' : 'secondary'}
                >
                  {translateStatus(item.status)}
                </Badge>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
