import { apiClient } from '@/services/apiClient';
import type {
  ExternalRentalItem,
  ExternalRentalSummary,
  ExternalRentalStatus,
} from '@/types/externalRentals';

interface ExternalRentalUpdatePayload {
  wearCount?: number;
  incrementWear?: number;
  returnDueDate?: string;
  status?: ExternalRentalStatus;
  notes?: string;
  rentalCost?: number;
}

export const fetchExternalRentalSummary = async (): Promise<ExternalRentalSummary> => {
  return apiClient.get<ExternalRentalSummary>('/api/v2/external-rentals/summary');
};

export const updateExternalRentalItem = async (
  itemId: string,
  payload: ExternalRentalUpdatePayload,
): Promise<ExternalRentalItem> => {
  return apiClient.patch<ExternalRentalItem>(
    `/api/v2/external-rentals/${itemId}`,
    payload,
  );
};
