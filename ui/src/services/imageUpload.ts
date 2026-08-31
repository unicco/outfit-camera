// services/imageUpload.ts

import { logger } from '@/utils/logger';

export interface ImageUploadResponse {
  id: string;
  original_url: string;
  thumbnails: {
    thumb_200: string;
    thumb_400: string;
  };
  size: number;
  content_type: string;
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export class ImageUploadService {
  private apiUrl: string;

  constructor(apiUrl: string) {
    this.apiUrl = apiUrl;
  }

  async uploadItemImages(
    itemId: string,
    files: File[],
    onProgress?: (progress: UploadProgress) => void
  ): Promise<ImageUploadResponse[]> {
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
    });

    // Create XMLHttpRequest for progress tracking
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      // Progress tracking
      if (onProgress) {
        xhr.upload.addEventListener('progress', event => {
          if (event.lengthComputable) {
            const progress: UploadProgress = {
              loaded: event.loaded,
              total: event.total,
              percentage: Math.round((event.loaded / event.total) * 100),
            };
            onProgress(progress);
          }
        });
      }

      // Handle completion
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const result = JSON.parse(xhr.responseText);
            resolve(result.uploaded_images || []);
          } catch {
            reject(new Error('Failed to parse response'));
          }
        } else {
          logger.error('Image upload server error:', {
            status: xhr.status,
            statusText: xhr.statusText,
            responseText: xhr.responseText,
            responseHeaders: xhr.getAllResponseHeaders(),
            timestamp: new Date().toISOString()
          });

          try {
            const error = JSON.parse(xhr.responseText);
            reject(
              new Error(
                error.detail || `Upload failed with status ${xhr.status}: ${xhr.statusText}`
              )
            );
          } catch {
            reject(new Error(`Upload failed with status ${xhr.status}: ${xhr.statusText}. Response: ${xhr.responseText}`));
          }
        }
      });

      // Handle errors
      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'));
      });

      xhr.addEventListener('abort', () => {
        reject(new Error('Upload aborted'));
      });

      // Set timeout (120 seconds - background processing continues)
      xhr.timeout = 120000;

      xhr.addEventListener('timeout', () => {
        reject(new Error('アップロードタイムアウト（バックグラウンド処理は継続されます）'));
      });

      // Send request
      xhr.open('POST', `${this.apiUrl}/api/v2/wardrobe/items/${itemId}/images`);
      xhr.send(formData);
    });
  }

  async uploadSingleImage(
    itemId: string,
    file: File,
    onProgress?: (progress: UploadProgress) => void
  ): Promise<ImageUploadResponse> {
    const results = await this.uploadItemImages(itemId, [file], onProgress);
    if (results.length === 0) {
      throw new Error('No image was uploaded');
    }
    return results[0];
  }

  // Helper method to validate files before upload
  validateFiles(files: File[]): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    const maxSize = 10 * 1024 * 1024; // 10MB
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];

    files.forEach((file, index) => {
      if (!allowedTypes.includes(file.type)) {
        errors.push(
          `ファイル ${index + 1}: サポートされていない形式です (${file.type})`
        );
      }
      if (file.size > maxSize) {
        errors.push(
          `ファイル ${index + 1}: ファイルサイズが大きすぎます (最大10MB)`
        );
      }
    });

    return {
      valid: errors.length === 0,
      errors,
    };
  }
}

// Singleton instance factory
let serviceInstance: ImageUploadService | null = null;

export function getImageUploadService(apiUrl: string): ImageUploadService {
  if (!serviceInstance || serviceInstance['apiUrl'] !== apiUrl) {
    serviceInstance = new ImageUploadService(apiUrl);
  }
  return serviceInstance;
}
