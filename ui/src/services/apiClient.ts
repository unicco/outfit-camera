/* eslint-disable no-restricted-globals */
// ApiClient 内部では fetch() の使用が必要
import { API_TIMEOUT, API_ERROR_MESSAGES } from '../config/api';
import { transformApiResponse, transformForApiRequest } from '../utils/apiResponseTransformer';

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

type ReadOnlyState = {
  enabled: boolean;
  reason?: string;
};

const readOnlyState: ReadOnlyState = {
  enabled: false,
};

export interface ApiError extends Error {
  status?: number;
  statusText?: string;
  body?: unknown;
}

export interface ApiRequestOptions extends Omit<RequestInit, 'body' | 'mode'> {
  body?: unknown;
  timeout?: number;
  skipTransform?: boolean;
  mode?: RequestMode; // 'cors' | 'no-cors' | 'same-origin' | 'navigate'
}

export function setReadOnlyMode(enabled: boolean, reason?: string): void {
  readOnlyState.enabled = enabled;
  readOnlyState.reason = reason;
}

export function isReadOnlyModeEnabled(): boolean {
  return readOnlyState.enabled;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl = '') {
    this.baseUrl = baseUrl;
  }

  async get<T = unknown>(path: string, options?: ApiRequestOptions): Promise<T> {
    return this.request<T>('GET', path, options);
  }

  async post<T = unknown>(path: string, data?: unknown, options?: ApiRequestOptions): Promise<T> {
    return this.request<T>('POST', path, { ...options, body: data });
  }

  async put<T = unknown>(path: string, data?: unknown, options?: ApiRequestOptions): Promise<T> {
    return this.request<T>('PUT', path, { ...options, body: data });
  }

  async delete<T = unknown>(path: string, options?: ApiRequestOptions): Promise<T> {
    return this.request<T>('DELETE', path, options);
  }

  async patch<T = unknown>(path: string, data?: unknown, options?: ApiRequestOptions): Promise<T> {
    return this.request<T>('PATCH', path, { ...options, body: data });
  }

  async head(path: string, options?: ApiRequestOptions): Promise<Response> {
    return this.requestRaw('HEAD', path, options);
  }

  async upload<T = unknown>(path: string, formData: FormData, options?: ApiRequestOptions): Promise<T> {
    return this.request<T>('POST', path, {
      ...options,
      // DEFAULT(5秒) ではファイルアップロードに足りない。明示がなければ FILE_UPLOAD。
      timeout: options?.timeout ?? API_TIMEOUT.FILE_UPLOAD,
      body: formData,
      skipTransform: true,
    });
  }

  private async request<T>(
    method: string,
    path: string,
    options: ApiRequestOptions = {}
  ): Promise<T> {
    if (MUTATING_METHODS.has(method.toUpperCase()) && readOnlyState.enabled) {
      const error = new Error(
        readOnlyState.reason || '現在のアカウントは閲覧専用モードのため、更新操作はできません。'
      ) as ApiError;
      error.status = 403;
      error.statusText = 'Forbidden';
      error.body = {
        detail: error.message,
        readOnly: true,
      };
      throw error;
    }

    const {
      body,
      timeout = API_TIMEOUT.DEFAULT,
      skipTransform = false,
      headers = {},
      ...fetchOptions
    } = options;

    const url = `${this.baseUrl}${path}`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      let processedBody: BodyInit | undefined;
      const processedHeaders = new Headers(headers);

      if (body !== undefined && method !== 'GET') {
        if (body instanceof FormData) {
          processedBody = body;
        } else {
          const transformedBody = skipTransform ? body : transformForApiRequest(body);
          processedBody = JSON.stringify(transformedBody);
          if (!processedHeaders.has('Content-Type')) {
            processedHeaders.set('Content-Type', 'application/json');
          }
        }
      }

      const response = await fetch(url, {
        ...fetchOptions,
        method,
        headers: processedHeaders,
        body: processedBody,
        signal: controller.signal,
        mode: options.mode,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw await this.createApiError(response);
      }

      if (response.status === 204 || response.headers.get('content-length') === '0') {
        return undefined as unknown as T;
      }

      const contentType = response.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        const data = await response.json();
        return skipTransform ? data : transformApiResponse<T>(data);
      }

      return (await response.text()) as unknown as T;
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw this.createTimeoutError();
        }
        throw error;
      }

      throw Object.assign(new Error(API_ERROR_MESSAGES.NETWORK), { cause: error });
    }
  }

  private async createApiError(response: Response): Promise<ApiError> {
    const error = new Error() as ApiError;
    error.status = response.status;
    error.statusText = response.statusText;

    try {
      const contentType = response.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        error.body = await response.json();
        error.message = (error.body as { detail?: string })?.detail ||
                       `${response.status} ${response.statusText}`;
      } else {
        const text = await response.text();
        error.message = text || `${response.status} ${response.statusText}`;
        error.body = text;
      }
    } catch {
      error.message = `${response.status} ${response.statusText}`;
    }

    switch (response.status) {
      case 404:
        error.message = API_ERROR_MESSAGES.NOT_FOUND;
        break;
      case 500:
      case 502:
      case 503:
      case 504:
        error.message = API_ERROR_MESSAGES.SERVER;
        break;
    }

    return error;
  }

  private createTimeoutError(): ApiError {
    const error = new Error(API_ERROR_MESSAGES.TIMEOUT) as ApiError;
    error.name = 'TimeoutError';
    return error;
  }

  private async requestRaw(
    method: string,
    path: string,
    options: ApiRequestOptions = {}
  ): Promise<Response> {
    const {
      timeout = API_TIMEOUT.DEFAULT,
      headers = {},
      ...fetchOptions
    } = options;

    const url = `${this.baseUrl}${path}`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        ...fetchOptions,
        method,
        headers: new Headers(headers),
        signal: controller.signal,
        mode: options.mode,
      });

      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw this.createTimeoutError();
        }
        throw error;
      }

      throw Object.assign(new Error(API_ERROR_MESSAGES.NETWORK), { cause: error });
    }
  }
}

// Vite環境変数からAPI URLを取得（デフォルトは空文字列）
// 注意: 現在のコードベースでは apiClient.get('/api/v2/...') のように使用されているため、
// baseURLは空文字列にする必要がある
const apiUrl: string = import.meta.env.VITE_API_URL ?? '';
export const apiClient = new ApiClient(apiUrl);
