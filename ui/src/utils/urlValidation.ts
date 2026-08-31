/**
 * URL validation utilities
 */

/**
 * Validates if a URL is a valid HTTP or HTTPS URL
 * @param url - URL to validate
 * @returns true if valid HTTP/HTTPS URL, false otherwise
 */
export const isValidHttpUrl = (url?: string | null): boolean => {
  return Boolean(url && (url.startsWith('http://') || url.startsWith('https://')));
};

/**
 * Validates if a URL is a valid HTTPS URL (secure only)
 * @param url - URL to validate
 * @returns true if valid HTTPS URL, false otherwise
 */
export const isValidHttpsUrl = (url?: string | null): boolean => {
  return Boolean(url && url.startsWith('https://'));
};

/**
 * Validates if a URL is a valid GCS (Google Cloud Storage) URL
 * @param url - URL to validate
 * @returns true if valid GCS URL, false otherwise
 */
export const isValidGcsUrl = (url?: string | null): boolean => {
  return Boolean(
    url &&
    (url.startsWith('https://storage.googleapis.com/') ||
     url.startsWith('https://storage.cloud.google.com/') ||
     url.includes('.storage.googleapis.com/'))
  );
};
