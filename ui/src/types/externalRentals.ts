export type ExternalRentalStatus = 'ACTIVE' | 'RETURNED';

export interface ExternalRentalItem {
  id: string;
  source: string;
  name: string;
  brand?: string | null;
  size?: string | null;
  managementNumber?: string | null;
  returnDueDate?: string | null;
  status: ExternalRentalStatus;
  wearCount: number;
  lastWornAt?: string | null;
  capturedAt?: string | null;
  returnedAt?: string | null;
  daysUntilDue?: number | null;
  rentalCost?: number | null;
  costPerWear?: number | null;
  imageUrl?: string | null;
}

export interface ExternalRentalSummary {
  planCost: number;
  totalWearCount: number;
  costPerWear?: number | null;
  activeItemCount: number;
  items: ExternalRentalItem[];
  returnedItems?: ExternalRentalItem[];
}
