/**
 * AI 衣類検出関連の型定義 (Issue #105)
 */

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
}

export interface DetectedClothingItem {
  category: string;
  subcategory?: string;
  confidence: number;
  bbox: BoundingBox;
  colorPrimary?: string;
  colorSecondary?: string;
  croppedImageUrl?: string;
  wardrobeMatchCandidates: WardrobeMatchCandidate[];
}

export interface WardrobeMatchCandidate {
  itemId: string;
  name: string;
  category: string;
  colorPrimary?: string;
  colorSecondary?: string;
  imageUrls: string[] | { [key: string]: string };
  similarityScore?: number; // New field for optimized matching
  matchScore?: number; // Legacy field for backwards compatibility
  matchReason: string;
}

export interface ClothingDetectionResult {
  photoId: string;
  detectionCount: number;
  detectedItems: DetectedClothingItem[];
  processingTimeMs: number;
  modelVersion: string;
  annotatedImageUrl?: string;
}

export interface ClothingDetectionRequest {
  photoId: string;
  cropItems?: boolean;
  matchWardrobe?: boolean;
  annotateImage?: boolean;
}

export interface AIDetectionStatus {
  status: 'available' | 'unavailable';
  modelLoaded: boolean;
  confidenceThreshold?: number;
  supportedCategories?: string[];
  error?: string;
}
