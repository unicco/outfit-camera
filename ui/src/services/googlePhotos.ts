import { apiClient } from './apiClient';

export interface GooglePhotosBatchUploadRequestItem {
  clientId: string;
  file: File;
  captureTime?: string | null;
  locationName?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface GooglePhotosBatchUploadResult {
  fileName: string;
  clientId?: string;
  success: boolean;
  mediaItemId?: string;
  error?: string;
}

export interface GooglePhotosBatchUploadResponse {
  success: boolean;
  results: GooglePhotosBatchUploadResult[];
}

export function createBatchUploadFormData(
  items: GooglePhotosBatchUploadRequestItem[]
): FormData {
  const formData = new FormData();
  const metadataPayload = items.map(item => ({
    clientId: item.clientId,
    fileName: item.file.name,
    captureTime: item.captureTime ?? null,
    locationName: item.locationName ?? null,
    latitude:
      typeof item.latitude === 'number' && Number.isFinite(item.latitude)
        ? item.latitude
        : null,
    longitude:
      typeof item.longitude === 'number' && Number.isFinite(item.longitude)
        ? item.longitude
        : null,
  }));

  formData.append('metadata_json', JSON.stringify(metadataPayload));

  items.forEach(item => {
    formData.append('files', item.file, item.file.name);
  });

  return formData;
}

export async function uploadGooglePhotosBatch(
  formData: FormData
): Promise<GooglePhotosBatchUploadResponse> {
  return apiClient.upload<GooglePhotosBatchUploadResponse>(
    '/api/v2/google-photos/batch-upload',
    formData
  );
}
