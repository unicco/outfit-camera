/**
 * Wardrobe item constants for forms and UI components
 * Centralized management of categories, colors, seasons, and subcategories
 */

export interface CategoryOption {
  value: string;
  label: string;
  icon?: Record<string, unknown>; // For icon components if needed
}

export interface ColorOption {
  value: string;
  label: string;
  hex: string;
}

export interface SeasonOption {
  value: string;
  label: string;
}

// Categories - Standardized across all components
export const WARDROBE_CATEGORIES: CategoryOption[] = [
  { value: 'TOPS', label: 'トップス' },
  { value: 'BOTTOMS', label: 'ボトムス' },
  { value: 'OUTERWEAR', label: 'アウター' },
  { value: 'DRESSES', label: 'ワンピース' },
  { value: 'SHOES', label: 'シューズ' },
  { value: 'ACCESSORIES', label: 'アクセサリー' },
  { value: 'BAG', label: 'バッグ' },
  { value: 'SETS', label: 'セットアップ' },
  { value: 'OTHER', label: 'その他' },
];

// Subcategories - Organized by main category
export const WARDROBE_SUBCATEGORIES: Record<string, string[]> = {
  TOPS: [
    'カットソー',
    'T シャツ',
    'シャツ',
    'ポロシャツ',
    'ニット',
    'スウェット',
    'パーカー',
    'ベスト',
    'タンクトップ',
    'キャミソール',
    'カーディガン',
  ],
  BOTTOMS: [
    'ジーンズ',
    'チノパン',
    'スラックス',
    'スカート',
    'レギンス',
    'イージーパンツ',
  ],
  OUTERWEAR: ['ジャケット', 'コート', 'ブルゾン', 'ダウン', 'レインコート'],
  DRESSES: ['カジュアル', 'フォーマル'],
  SHOES: [
    'スニーカー',
    '革靴',
    'ブーツ',
    'サンダル',
    'ローファー',
    'パンプス',
    'ヒール',
  ],
  ACCESSORIES: [
    '帽子',
    'ベルト',
    'ネクタイ',
    'マフラー',
    '手袋',
    '時計',
    'メガネ',
    'ネックレス',
    'イヤリング',
  ],
  BAG: [
    'リュック',
    'トートバッグ',
    'ショルダーバッグ',
    'ブリーフケース',
    'ハンドバッグ',
    'クラッチバッグ',
  ],
  SETS: ['スーツ', 'セットアップ', 'コーディネート'],
  OTHER: ['ベルト', 'スカーフ', '手袋', 'マフラー', 'メガネ', 'サングラス', 'その他'],
};

// Colors - Standardized color palette
export const WARDROBE_COLORS: ColorOption[] = [
  { value: 'black', label: '黒', hex: '#000000' },
  { value: 'white', label: '白', hex: '#FFFFFF' },
  { value: 'gray', label: 'グレー', hex: '#808080' },
  { value: 'red', label: '赤', hex: '#FF0000' },
  { value: 'blue', label: '青', hex: '#0000FF' },
  { value: 'navy', label: 'ネイビー', hex: '#000080' },
  { value: 'green', label: '緑', hex: '#008000' },
  { value: 'yellow', label: '黄色', hex: '#FFFF00' },
  { value: 'orange', label: 'オレンジ', hex: '#FFA500' },
  { value: 'pink', label: 'ピンク', hex: '#FFC0CB' },
  { value: 'purple', label: '紫', hex: '#800080' },
  { value: 'brown', label: '茶色', hex: '#A52A2A' },
  { value: 'beige', label: 'ベージュ', hex: '#F5F5DC' },
  { value: 'khaki', label: 'カーキ', hex: '#F0E68C' },
  { value: 'silver', label: 'シルバー', hex: '#C0C0C0' },
  { value: 'gold', label: 'ゴールド', hex: '#FFD700' },
  { value: 'other', label: 'その他', hex: '#000000' },
];

// Seasons - Standard seasonal categories
export const WARDROBE_SEASONS: SeasonOption[] = [
  { value: 'spring', label: '春' },
  { value: 'summer', label: '夏' },
  { value: 'autumn', label: '秋' },
  { value: 'winter', label: '冬' },
];

// Occasions - 専用・特別な場（TPO）。値は日本語ラベルそのまま（life-log から日本語で絞り込む）。
// 日常で重複するシーン（カジュアル・ビジネス会・友だち会 等）は tags で運用する。
export const WARDROBE_OCCASIONS: SeasonOption[] = [
  { value: '冠婚葬祭', label: '冠婚葬祭' },
  { value: 'フォーマル', label: 'フォーマル' },
  { value: 'ゴルフ', label: 'ゴルフ' },
  { value: 'スポーツ', label: 'スポーツ' },
  { value: 'アウトドア', label: 'アウトドア' },
];

// Patterns - Common clothing patterns
export const WARDROBE_PATTERNS: string[] = [
  '無地',
  'ストライプ',
  'チェック',
  'ドット',
  '花柄',
  '幾何学模様',
  'ボーダー',
  'プリント',
  'その他',
];

// Materials - Common clothing materials
export const WARDROBE_MATERIALS: string[] = [
  'コットン',
  'ポリエステル',
  'ウール',
  'シルク',
  'リネン',
  'デニム',
  'レザー',
  'ナイロン',
  'カシミア',
  'その他',
];

// Size options - Standard clothing sizes
export const WARDROBE_SIZES: string[] = [
  'XS',
  'S',
  'M',
  'L',
  'XL',
  'XXL',
  'フリーサイズ',
];

// Helper functions
export const getCategoryLabel = (value: string): string => {
  return WARDROBE_CATEGORIES.find(cat => cat.value === value)?.label || value;
};

export const getColorLabel = (value: string): string => {
  return WARDROBE_COLORS.find(color => color.value === value)?.label || value;
};

export const getColorHex = (value: string): string => {
  return WARDROBE_COLORS.find(color => color.value === value)?.hex || '#000000';
};

export const getSeasonLabel = (value: string): string => {
  return (
    WARDROBE_SEASONS.find(season => season.value === value)?.label || value
  );
};

export const getOccasionLabel = (value: string): string => {
  return (
    WARDROBE_OCCASIONS.find(occasion => occasion.value === value)?.label || value
  );
};

export const getSubcategories = (category: string): string[] => {
  return WARDROBE_SUBCATEGORIES[category] || [];
};

// Status options for wardrobe items
export const WARDROBE_STATUSES = [
  { value: 'ACTIVE', label: 'アクティブ' },
  { value: 'DISPOSAL_CONSIDERATION', label: '処分検討中' },
  { value: 'SELLING', label: '出品中' },
  { value: 'DISPOSED', label: '処分済' },
];

export const getStatusLabel = (value: string): string => {
  return (
    WARDROBE_STATUSES.find(status => status.value === value)?.label || value
  );
};

// Sale platforms for issue #823
export const SALE_PLATFORMS = [
  { value: 'mercari', label: 'メルカリ' },
  { value: 'zozoused', label: 'ZOZOUSED' },
  { value: 'yahoo_auction', label: 'ヤフオク' },
  { value: 'other', label: 'その他' },
];

export const getSalePlatformLabel = (value: string): string => {
  return (
    SALE_PLATFORMS.find(platform => platform.value === value)?.label || value
  );
};

export const getCategorySubcategoryDisplay = (
  category: string,
  subcategory?: string
): string => {
  const categoryLabel = getCategoryLabel(category);
  if (subcategory) {
    return `${categoryLabel} > ${subcategory}`;
  }
  return categoryLabel;
};
