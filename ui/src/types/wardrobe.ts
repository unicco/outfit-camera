/**
 * 画像URL形式の型定義
 */
export interface ImageUrls {
  original?: string;
  thumbnails?: Record<string, string>;
}

/**
 * 衣類アイテムの基本型定義
 */
export interface ClothingItem {
  id: string;
  name: string;
  category: string;
  color: string;
  pattern?: string;
  material?: string;
  brand?: string;
  season?: string[];
  tags?: string[];
  size?: string;
  purchaseDate?: string;
  purchasePrice?: number;
  purchaseLocation?: string;
  // Sale information (issue #823)
  salePlatform?: string;
  salePrice?: number;
  saleCommission?: number;
  disposalDate?: string;
  // Calculated sale fields
  saleNetAmount?: number;
  saleProfitLoss?: number;
  imageUrls?: string[] | ImageUrls; // 新旧両対応
  cloudinaryPublicIds?: string[];
  createdAt: string;
  updatedAt: string;
  lastWorn?: string;
  wearCount: number;
  userId?: string;
  lastUsedDate?: string;  // バックエンド互換性
  defaultUsageCount?: number;
  usageCount?: number;
  careInstructions?: string;
  notes?: string;
  isFavorite?: boolean;
  status?: 'active' | 'disposal_consideration' | 'selling' | 'disposed';

  // AI recommendation fields (populated when photo_id is provided)
  aiRanking?: number;  // 1-3 for top recommendations
  aiMatchScore?: number;  // Similarity score
  isAiRecommended?: boolean;  // True if in top 3
}

/**
 * 色パレットの個別色情報
 */
export interface ColorPaletteColor {
  hex: string;
  position: number;
  rgb?: { r: number; g: number; b: number };
}

/**
 * 色パレット全体の型定義
 */
export interface ColorsPalette {
  palette: ColorPaletteColor[];
  extractionMethod?: string;
}

/**
 * 拡張衣類アイテム型（API互換性のため）
 */
export interface ExtendedClothingItem extends Omit<ClothingItem, 'status'> {
  subcategory?: string;
  colorPrimary?: string;
  colorSecondary?: string;
  colorsPalette?: ColorsPalette; // 新しい5色パレット
  colorDistribution?: Record<string, number>;
  occasion?: string[];
  costPerWear?: number;
  status?: 'active' | 'disposal_consideration' | 'selling' | 'disposed';
  disposalDate?: string;
  defaultUsageCount?: number;
  actualUsageCount?: number;
  embeddingModelVersion?: string;
  embeddingComputedAt?: string;
  embeddingVector?: number[];
  imageMetadata?: Record<string, unknown>;
}

/**
 * コーディネート型定義
 */
export interface Outfit {
  id: string;
  date: string;
  occasion?: string;
  location?: string;
  weather?: string;
  notes?: string;
  photos: OutfitPhoto[];
  items: ClothingItem[];
  tags?: string[];
  createdAt: string;
  updatedAt: string;
  userId?: string;
}

/**
 * コーディネート写真の型定義
 */
export interface OutfitPhoto {
  id: string;
  cloudinaryPublicId: string;
  url: string;
  thumbnailUrl?: string;
  uploadTimestamp: string;
  isPrimary: boolean;
  outfitId: string;
}

/**
 * ワードローブ統計情報の型定義
 */
export interface WardrobeStats {
  totalItems: number;
  byCategory: Record<string, number>;
  byColor: Record<string, number>;
  bySeason: Record<string, number>;
  frequentlyWorn: ClothingItem[];
  recentlyAdded: ClothingItem[];
}

/**
 * ワードローブマッチング候補の型定義
 * AI検出でマッチしたワードローブアイテム情報
 */
export interface WardrobeMatchCandidate {
  itemId?: string;
  id?: string;  // Legacy support
  name?: string;
  category?: string;
  color?: string;
  imagePath?: string;
  imageUrls?: {
    original?: string;
    thumbnails?: {
      thumb_200?: string;  // Note: 数字付きアンダースコアは変換されない
      thumb_400?: string;  // Note: 数字付きアンダースコアは変換されない
    };
  };
  description?: string;
  aiRanking?: number;
  similarityScore: number;
  matchReason?: string;
}
