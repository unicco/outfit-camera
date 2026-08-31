import { useCallback } from 'react';

import { apiClient } from '@/services/apiClient';
import type {
  Photo,
  OutfitRecord,
  OutfitExternalRentalItem,
  OutfitRecordDateRange,
} from '@/types/outfit';
import type { ExternalRentalItem } from '@/types/externalRentals';
import { logger } from '@/utils/logger';

type ExistingSelection = {
  clothingItemIds: string[];
  externalRentalItemIds: string[];
  rentalDetails: Record<string, ExternalRentalItem>;
};

interface UseExistingOutfitRecordParams {
  photo: Photo;
  selectedDate: string;
  setSelectedItems: React.Dispatch<React.SetStateAction<string[]>>;
  setSelectedRentalItems: React.Dispatch<React.SetStateAction<string[]>>;
  setSelectedRentalDetails: React.Dispatch<
    React.SetStateAction<Record<string, ExternalRentalItem>>
  >;
}

interface UseExistingOutfitRecordResult {
  fetchExistingOutfitRecord: () => Promise<void>;
}

export const useExistingOutfitRecord = ({
  photo,
  selectedDate,
  setSelectedItems,
  setSelectedRentalItems,
  setSelectedRentalDetails,
}: UseExistingOutfitRecordParams): UseExistingOutfitRecordResult => {
  // 写真ベースの既存recordを取得
  const fetchPhotoBasedRecord = useCallback(async (): Promise<ExistingSelection> => {
    try {
      const existingRecord = await apiClient.get<OutfitRecord | null>(
        `/api/v2/outfits/photo/${photo.id}`,
      );
      if (!existingRecord) {
        return {
          clothingItemIds: [],
          externalRentalItemIds: [],
          rentalDetails: {},
        };
      }

      const clothingItemIds: string[] = [];
      if (existingRecord.outfitItems && Array.isArray(existingRecord.outfitItems)) {
        clothingItemIds.push(
          ...existingRecord.outfitItems.map(item => item.clothingItemId),
        );
      } else if (
        (existingRecord as Record<string, unknown>).clothingItems &&
        Array.isArray((existingRecord as Record<string, unknown>).clothingItems)
      ) {
        const clothingItems = (existingRecord as Record<string, unknown>).clothingItems as Array<
          Record<string, unknown>
        >;
        clothingItemIds.push(
          ...clothingItems
            .map(item => item.id as string | undefined)
            .filter((id): id is string => Boolean(id)),
        );
      } else if (
        (existingRecord as Record<string, unknown>).clothingItemIds &&
        Array.isArray((existingRecord as Record<string, unknown>).clothingItemIds)
      ) {
        clothingItemIds.push(
          ...((existingRecord as Record<string, unknown>).clothingItemIds as string[]),
        );
      }

      const rentalDetails: Record<string, ExternalRentalItem> = {};
      const rentalItemIds: string[] =
        existingRecord.externalRentalItems?.map((link: OutfitExternalRentalItem) => {
          if (link.externalRentalItem) {
            rentalDetails[link.externalRentalItemId] = link.externalRentalItem;
          }
          return link.externalRentalItemId;
        }) ?? existingRecord.externalRentalItemIds ?? [];

      return {
        clothingItemIds,
        externalRentalItemIds: rentalItemIds,
        rentalDetails,
      };
    } catch (error) {
      logger.error('Failed to fetch existing outfit record:', error);
      return {
        clothingItemIds: [],
        externalRentalItemIds: [],
        rentalDetails: {},
      };
    }
  }, [photo.id]);

  // 日付ベースの既存recordを取得
  const fetchDateBasedRecord = useCallback(async (): Promise<ExistingSelection> => {
    try {
      const outfitRecords = await apiClient.get<OutfitRecordDateRange[]>(
        `/api/v2/outfits/date-range?start_date=${selectedDate}&end_date=${selectedDate}`,
      );
      if (Array.isArray(outfitRecords) && outfitRecords.length > 0) {
        const firstRecord = outfitRecords[0];
        const clothingItemIds =
          firstRecord.clothingItems?.map(item => item.id) ?? [];
        const rentalItems =
          firstRecord.externalRentalItems ||
          (firstRecord as Record<string, unknown>).external_rental_items ||
          [];
        const rentalItemIds =
          firstRecord.externalRentalItemIds ??
          (rentalItems as ExternalRentalItem[]).map(item => item.id);
        const rentalDetails: Record<string, ExternalRentalItem> = {};
        for (const item of rentalItems as ExternalRentalItem[]) {
          rentalDetails[item.id] = item;
        }
        return {
          clothingItemIds,
          externalRentalItemIds: rentalItemIds,
          rentalDetails,
        };
      }
      return {
        clothingItemIds: [],
        externalRentalItemIds: [],
        rentalDetails: {},
      };
    } catch (error) {
      logger.error('Failed to fetch date-based outfit record:', error);
      return {
        clothingItemIds: [],
        externalRentalItemIds: [],
        rentalDetails: {},
      };
    }
  }, [selectedDate]);

  // 既存のoutfit recordを取得
  const fetchExistingOutfitRecord = useCallback(async (): Promise<void> => {
    try {
      const hasSelection = (selection: ExistingSelection): boolean =>
        selection.clothingItemIds.length > 0 ||
        selection.externalRentalItemIds.length > 0;

      let existingSelection: ExistingSelection;

      if (photo.id && photo.id.trim() !== '') {
        const photoBasedSelection = await fetchPhotoBasedRecord();
        if (hasSelection(photoBasedSelection) || !selectedDate) {
          existingSelection = photoBasedSelection;
        } else {
          const dateBasedSelection = await fetchDateBasedRecord();
          existingSelection = hasSelection(dateBasedSelection)
            ? dateBasedSelection
            : photoBasedSelection;
        }
      } else {
        existingSelection = await fetchDateBasedRecord();
      }

      setSelectedItems(existingSelection.clothingItemIds);
      setSelectedRentalItems(existingSelection.externalRentalItemIds);
      if (Object.keys(existingSelection.rentalDetails).length > 0) {
        setSelectedRentalDetails(prev => ({
          ...prev,
          ...existingSelection.rentalDetails,
        }));
      }
    } catch (error) {
      logger.error('Failed to fetch existing outfit record:', error);
      setSelectedItems([]);
      setSelectedRentalItems([]);
    }
  }, [
    photo.id,
    selectedDate,
    fetchDateBasedRecord,
    fetchPhotoBasedRecord,
    setSelectedItems,
    setSelectedRentalItems,
    setSelectedRentalDetails,
  ]);

  return {
    fetchExistingOutfitRecord,
  };
};
