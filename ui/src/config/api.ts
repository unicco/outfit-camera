/**
 * API configuration constants
 */

import {
  transformApiResponse,
  transformForApiRequest,
} from '../utils/apiResponseTransformer';
import { apiClient } from '../services/apiClient';

// タイムアウト設定
export const API_TIMEOUT = {
  DEFAULT: 5000, // 5秒 - 通常のAPI呼び出し
  LONG_RUNNING: 8000, // 8秒 - 重い処理（写真取得など）
  // 朝ブリーフ（/today）は天気 + ICS フェッチ + 過去コーデ集約で ~9 秒かかる重い
  // 集約エンドポイント。DEFAULT(5秒) だと abort して「コーデを取得できませんでした」に
  // なるため専用に長めを取る。
  MORNING_BRIEF: 25000, // 25秒
  FILE_UPLOAD: 30000, // 30秒 - ファイルアップロード
  // FILE_UPLOAD と同値だが用途が違う。片方だけ変えられるよう別名にする。
  AI_ANALYSIS: 30000, // 30秒 - AI 分析（/api/v2/unified/*）
} as const;

// エラーメッセージ
export const API_ERROR_MESSAGES = {
  TIMEOUT: 'API request timed out',
  NETWORK: 'Network connection failed',
  SERVER: 'Server error occurred',
  NOT_FOUND: 'Resource not found',
} as const;

/**
 * API 共通処理用ヘルパー
 */
export const ApiHelpers = {
  /**
   * レスポンスデータを UI 用に変換
   */
  transformResponse: transformApiResponse,

  /**
   * リクエストデータを API 用に変換
   */
  transformRequest: transformForApiRequest,

  /**
   * fetch ラッパー (レスポンス変換付き)
   * @deprecated Use apiClient directly instead
   */
  async fetchWithTransform<T = Record<string, unknown>>(
    url: string,
    options?: RequestInit
  ): Promise<T> {
    // ApiClient を使用するように変更
    const method = options?.method || 'GET';
    const body = options?.body ? JSON.parse(options.body as string) : undefined;

    switch (method.toUpperCase()) {
      case 'GET':
        return apiClient.get<T>(url, options);
      case 'POST':
        return apiClient.post<T>(url, body, options);
      case 'PUT':
        return apiClient.put<T>(url, body, options);
      case 'DELETE':
        return apiClient.delete<T>(url, options);
      case 'PATCH':
        return apiClient.patch<T>(url, body, options);
      default:
        throw new Error(`Unsupported method: ${method}`);
    }
  },
};
