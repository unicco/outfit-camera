/**
 * Image URL utility functions for wardrobe images
 */

/**
 * Gets proxy URL for GCS images to avoid CORS issues
 * @param imageUrl - The original image URL
 * @param apiUrl - The base API URL
 * @param itemId - The wardrobe item ID
 * @returns Proxy URL if GCS image, otherwise original URL
 */
export const getProxyImageUrl = (
  imageUrl: string | null,
  apiUrl: string,
  itemId: string
): string | null => {
  if (!imageUrl) return null;

  // For GCS images, use proxy to avoid CORS issues
  if (imageUrl.includes('storage.googleapis.com')) {
    return `${apiUrl}/api/v2/wardrobe/items/${itemId}/image-proxy`;
  }
  return imageUrl;
};

/**
 * Constructs a proper image URL from a relative or absolute path
 * @param imageUrl - The image URL from the API (can be relative or absolute)
 * @param apiUrl - The base API URL
 * @returns Properly formatted absolute URL
 */
export const getImageUrl = (imageUrl: string, apiUrl: string): string => {
  if (!imageUrl) {
    return '';
  }

  // If already an absolute URL, return as-is
  if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
    return imageUrl;
  }

  // Handle relative URLs - ensure they start with /
  const cleanUrl = imageUrl.startsWith('/') ? imageUrl : `/${imageUrl}`;
  const cleanApiUrl = apiUrl.replace(/\/$/, ''); // Remove trailing slash
  const finalUrl = `${cleanApiUrl}${cleanUrl}`;

  return finalUrl;
};

/**
 * Gets the thumbnail URL for a wardrobe item image
 * @param imageUrl - The original image URL
 * @param apiUrl - The base API URL
 * @param size - Thumbnail size (200 or 400)
 * @returns Thumbnail URL or original URL if thumbnail not available
 */
export const getThumbnailUrl = (
  imageUrl: string,
  apiUrl: string,
  size: 200 | 400 = 200
): string => {
  if (!imageUrl) {
    return '';
  }

  // If it's already a thumbnail URL, return as-is
  if (imageUrl.includes('_thumb_')) {
    return getImageUrl(imageUrl, apiUrl);
  }

  // Try to construct thumbnail URL
  const baseUrl = getImageUrl(imageUrl, apiUrl);

  // For local storage URLs, replace the filename with thumbnail version
  if (baseUrl.includes('/static/wardrobe/')) {
    const urlParts = baseUrl.split('.');
    urlParts.pop(); // Remove extension
    const baseName = urlParts.join('.');
    const thumbnailUrl = `${baseName}_thumb_${size}.jpg`;
    return thumbnailUrl;
  }

  // For other URLs, return original
  return baseUrl;
};

/**
 * Validates if an image URL is accessible
 * @param imageUrl - The image URL to validate
 * @returns Promise that resolves to true if image is accessible
 */
export const validateImageUrl = async (imageUrl: string): Promise<boolean> => {
  if (!imageUrl) return false;

  try {
    // 外部 URL の検証のため fetch() を直接使用
    // eslint-disable-next-line no-restricted-globals
    const response = await fetch(imageUrl, { method: 'HEAD' });
    return response.ok;
  } catch {
    return false;
  }
};

/**
 * Gets the best available image URL from either array or dict format
 * @param imageUrls - Array of image URLs or dict with original/thumbnails
 * @param apiUrl - The base API URL
 * @param preferThumbnail - Whether to prefer thumbnail over original
 * @returns Best available image URL or empty string
 */
export const getBestImageUrl = (
  imageUrls:
    | string[]
    | { original?: string; thumbnails?: { [key: string]: string } }
    | null
    | undefined,
  apiUrl: string,
  preferThumbnail: boolean = false
): string => {
  if (!imageUrls) {
    return '';
  }

  // Handle new dict format
  if (typeof imageUrls === 'object' && !Array.isArray(imageUrls)) {
    if (preferThumbnail && imageUrls.thumbnails) {
      // Try to get the best thumbnail - prefer 400px for better quality
      const thumb400 = imageUrls.thumbnails.thumb_400;
      const thumb200 = imageUrls.thumbnails.thumb_200;

      if (thumb400) {
        return getImageUrl(thumb400, apiUrl);
      }
      if (thumb200) {
        return getImageUrl(thumb200, apiUrl);
      }
    }

    // Fallback to original
    if (imageUrls.original) {
      return getImageUrl(imageUrls.original, apiUrl);
    }

    return '';
  }

  // Handle old array format
  if (Array.isArray(imageUrls)) {
    if (imageUrls.length === 0) {
      return '';
    }

    const primaryUrl = imageUrls[0];

    if (preferThumbnail) {
      return getThumbnailUrl(primaryUrl, apiUrl);
    } else {
      return getImageUrl(primaryUrl, apiUrl);
    }
  }

  return '';
};
