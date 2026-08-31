// Simplified URL configuration for same-domain architecture
// Uses environment variables with simple fallbacks

// 許可されたCloudflareドメインのリスト（セキュリティ強化）
const ALLOWED_CLOUDFLARE_DOMAINS = ['coordinate.unicco.app'];

// より厳密なドメイン検証
const isAllowedDomain = (hostname: string): boolean => {
  // ホスト名の形式を検証（英数字、ハイフン、ドットのみ許可）
  const isValidFormat = /^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(hostname);
  return isValidFormat && ALLOWED_CLOUDFLARE_DOMAINS.includes(hostname);
};

// Tailscale CGNAT 範囲（100.64.0.0/10）の判定
// Caddy がリバースプロキシするため、相対 URL で統一できる
const isTailscaleIp = (hostname: string): boolean => {
  const match = hostname.match(/^100\.(\d+)\.\d+\.\d+$/);
  if (!match) return false;
  const second = parseInt(match[1], 10);
  return second >= 64 && second <= 127;
};

const getApiUrl = (): string => {
  const hostname = window.location.hostname;

  // 開発環境でのデバッグログ
  if (import.meta.env.DEV) {
    console.log(`[API URL Resolution] Hostname: ${hostname}`);
  }

  // Cloudflare Tunnel または Tailscale 経由の場合は相対URLを使用
  // Caddy がリバースプロキシするため同一オリジンでアクセス可能
  if (isAllowedDomain(hostname) || isTailscaleIp(hostname)) {
    if (import.meta.env.DEV) {
      console.log('[API URL Resolution] Using relative URL: /api');
    }
    return '/api';
  }

  // Always use environment variable first if set
  if (import.meta.env.VITE_API_URL) {
    if (import.meta.env.DEV) {
      console.log(`[API URL Resolution] Using env variable: ${import.meta.env.VITE_API_URL}`);
    }
    return import.meta.env.VITE_API_URL;
  }

  // Raspberry Pi local access
  if (hostname === 'pi-camera.local') {
    if (import.meta.env.DEV) {
      console.log('[API URL Resolution] Using Raspberry Pi URL: http://pi-camera.local:8000');
    }
    return 'http://pi-camera.local:8000';
  }

  // Default fallback for all cases
  if (import.meta.env.DEV) {
    console.log('[API URL Resolution] Using default: http://localhost:8000');
  }
  return 'http://localhost:8000';
};

const getCameraUrl = (): string => {
  const hostname = window.location.hostname;

  // Tailscale 経由のタッチスクリーン（Pi キオスク）はカメラに直接アクセス
  // VPS 経由の往復（Pi→VPS→Pi、RTT ~1s）を避けるため
  if (isTailscaleIp(hostname) && window.location.pathname.startsWith('/touchscreen')) {
    return 'http://localhost:8001';
  }

  // Cloudflare Tunnel または Tailscale 経由の場合は相対URLを使用
  if (isAllowedDomain(hostname) || isTailscaleIp(hostname)) {
    return '/camera';
  }

  // Always use environment variable first if set
  if (import.meta.env.VITE_CAMERA_URL) {
    return import.meta.env.VITE_CAMERA_URL;
  }

  // Raspberry Pi local access
  if (window.location.hostname === 'pi-camera.local') {
    return 'http://pi-camera.local:8001';
  }

  // Default fallback for all cases
  return 'http://localhost:8001';
};

export const API_URL = getApiUrl();
export const CAMERA_URL = getCameraUrl();


// Export individual service URLs for specific use cases
export const BACKEND_API_URL = API_URL;
export const API_BASE_URL = API_URL;
