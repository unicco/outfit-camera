import { Badge } from '@/components/ui/badge';
import { getBestImageUrl } from '@/utils/imageUtils';
import { API_URL } from '@/config/urls';
import type { ClothingItemWithSelection } from '@/types/outfit';

interface ClothingItemCheckboxProps {
  item: ClothingItemWithSelection;
  onToggle: (itemId: string) => void;
}

export function ClothingItemCheckbox({
  item,
  onToggle,
}: ClothingItemCheckboxProps) {
  const imageUrl = getBestImageUrl(item.imageUrls || [], API_URL);

  const getCategoryLabel = (category: string) => {
    const categoryMap: { [key: string]: string } = {
      TOPS: 'トップス',
      BOTTOMS: 'ボトムス',
      SHOES: 'シューズ',
      ACCESSORIES: 'アクセサリー',
      OUTERWEAR: 'アウター',
      DRESSES: 'ワンピース',
      SETS: 'セットアップ',
      BAG: 'バッグ',
      OTHER: 'その他',
    };
    return categoryMap[category] || category;
  };

  const getLastWornText = (lastWorn?: string) => {
    if (!lastWorn) return '未着用';

    const today = new Date();
    const wornDate = new Date(lastWorn);
    const diffTime = Math.abs(today.getTime() - wornDate.getTime());
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return '今日';
    if (diffDays === 1) return '昨日';
    if (diffDays < 7) return `${diffDays}日前`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}週間前`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)}ヶ月前`;
    return `${Math.floor(diffDays / 365)}年前`;
  };

  const handleItemClick = () => {
    onToggle(item.id);
  };

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.stopPropagation();
    onToggle(item.id);
  };

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
  };

  return (
    <div
      className="flex items-center p-3 border border-gray-200 rounded-lg hover:bg-gray-50 active:bg-gray-100 min-h-[60px] cursor-pointer"
      onClick={handleItemClick}
    >
      {/* Simple HTML checkbox for reliable interaction */}
      <input
        type="checkbox"
        checked={item.isSelected}
        onChange={handleCheckboxChange}
        onClick={handleCheckboxClick}
        className="w-5 h-5 mr-4 flex-shrink-0 cursor-pointer rounded border-gray-300 text-blue-600 focus:ring-blue-500"
        aria-label={`${item.name}を選択`}
      />

      {/* Item image */}
      <div className="w-12 h-12 mr-3 flex-shrink-0 rounded-lg overflow-hidden bg-gray-100">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={item.name}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-gray-400 text-xs">
            画像なし
          </div>
        )}
      </div>

      {/* Item information */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-medium text-gray-900 truncate">
            {item.name}
          </h3>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Badge variant="secondary" className="text-xs">
              {getCategoryLabel(item.category)}
            </Badge>
            {item.brand && (
              <span className="text-xs text-gray-500 truncate max-w-20">
                {item.brand}
              </span>
            )}
          </div>

          <span className="text-xs text-gray-500 flex-shrink-0">
            最終着用: {getLastWornText(item.lastWorn)}
          </span>
        </div>
      </div>
    </div>
  );
}
