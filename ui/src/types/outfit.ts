/**
 * Outfit-related type definitions
 * Issue #201 implementation
 */

import { ExtendedClothingItem, ImageUrls } from './wardrobe';
import type { ExternalRentalItem } from './externalRentals';

export interface OutfitExternalRentalItem {
  id: string;
  externalRentalItemId: string;
  createdAt: string;
  externalRentalItem?: ExternalRentalItem;
}

export interface OutfitRecord {
  id: string;
  photoId: string | null;
  photoUrl?: string;
  recordedAt: string;
  confidenceScore?: number;
  manualSelection: boolean;
  notes?: string;
  createdAt: string;
  updatedAt: string;
  outfitItems: OutfitItem[];
  externalRentalItems?: OutfitExternalRentalItem[];
  externalRentalItemIds?: string[];
}

export interface OutfitItem {
  id: string;
  outfitRecordId: string;
  clothingItemId: string;
  detectionConfidence?: number;
  manualAdded: boolean;
  positionX?: number;
  positionY?: number;
  createdAt: string;
  clothingItem?: ExtendedClothingItem;
}

export interface CreateOutfitRecordRequest {
  photoId?: string | null;
  clothingItemIds: string[];
  notes?: string;
  recordedAt?: string;  // 手動日付指定用 (ISO 8601 format)
  externalRentalItemIds?: string[];
}

export interface CreateOutfitRecordResponse {
  outfitRecordId: string;
  photoId: string | null;
  clothingItemsCount: number;
  message: string;
}

export interface PhotoClothingSelectionState {
  photo: Photo;
  clothingItems: ExtendedClothingItem[];
  selectedItems: string[];
  categoryFilter: string;
  searchQuery: string;
  isLoading: boolean;
  isSaving: boolean;
}

export interface Photo {
  id: string;
  filename: string;
  filePath: string;
  photoUrl?: string;
  thumbnailPath?: string;
  createdAt: string;
  updatedAt: string;
  capturedAt?: string;
  aiDetectionStatus?: 'pending' | 'processing' | 'completed' | 'failed';
  clothingItems?: ExtendedClothingItem[];
  // Add selectedDate for manual outfit creation
  selectedDate?: string; // YYYY-MM-DD format
  // Add outfitRecord if exists
  outfitRecord?: OutfitRecord;
}

export interface ClothingItemWithSelection extends ExtendedClothingItem {
  isSelected: boolean;
  lastWorn?: string;
}

export interface SimpleClothingItem {
  id: string;
  name: string;
  category: string;
  brand?: string;
  imageUrls?: string[] | ImageUrls;
}

export interface SimpleOutfitItem {
  id: string;
  clothingItem: SimpleClothingItem;
}

export interface SimpleOutfitRecord {
  id?: string;
  photoId: string | null;
  clothingItems: SimpleOutfitItem[];
  externalRentalItemIds?: string[];
}

// Date range endpoint response types
export interface DateRangeClothingItem {
  id: string;
  name: string;
  category: string;
  brand?: string;
  imageUrls?: ImageUrls | string[];
}

export interface OutfitRecordDateRange {
  date: string;
  outfitRecordId: string;
  photoId?: string;
  clothingItems: DateRangeClothingItem[];
  externalRentalItemIds?: string[];
  externalRentalItems?: ExternalRentalItem[];
}

export interface BatchOutfitRequest {
  photoIds: string[];
}

export interface BatchOutfitResponse {
  results: Record<string, SimpleOutfitRecord>;
}
