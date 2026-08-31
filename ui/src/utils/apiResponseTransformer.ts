/**
 * API レスポンス変換レイヤー
 * サーバー側 snake_case レスポンスと UI 側 camelCase 型定義の互換性を提供
 */

export type CaseTransformerOptions = {
  /**
   * 深くネストされたオブジェクトも変換するかどうか
   */
  deep?: boolean;
  /**
   * 配列内のオブジェクトも変換するかどうか
   */
  arrays?: boolean;
  /**
   * 変換をスキップするキーのリスト
   */
  skipKeys?: string[];
};

/**
 * snake_case を camelCase に変換
 */
export function toCamelCase(str: string): string {
  return str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
}

/**
 * camelCase を snake_case に変換
 */
export function toSnakeCase(str: string): string {
  return str.replace(/[A-Z]/g, letter => `_${letter.toLowerCase()}`);
}

/**
 * オブジェクトのキーを snake_case から camelCase に変換
 */
export function transformToCamelCase<T = Record<string, unknown>>(
  obj: Record<string, unknown> | unknown[] | unknown,
  options: CaseTransformerOptions = { deep: true, arrays: true }
): T {
  if (obj === null || obj === undefined) {
    return obj as T;
  }

  if (Array.isArray(obj)) {
    if (options.arrays) {
      return obj.map(item => transformToCamelCase(item, options)) as T;
    }
    return obj as T;
  }

  if (typeof obj !== 'object') {
    return obj as T;
  }

  const transformed: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(obj)) {
    // スキップするキーの場合はそのまま
    if (options.skipKeys?.includes(key)) {
      transformed[key] = value;
      continue;
    }

    const camelKey = toCamelCase(key);

    if (options.deep && value && typeof value === 'object') {
      transformed[camelKey] = transformToCamelCase(value, options);
    } else {
      transformed[camelKey] = value;
    }
  }

  return transformed as T;
}

/**
 * オブジェクトのキーを camelCase から snake_case に変換
 */
export function transformToSnakeCase<T = Record<string, unknown>>(
  obj: Record<string, unknown> | unknown[] | unknown,
  options: CaseTransformerOptions = { deep: true, arrays: true }
): T {
  if (obj === null || obj === undefined) {
    return obj as T;
  }

  if (Array.isArray(obj)) {
    if (options.arrays) {
      return obj.map(item => transformToSnakeCase(item, options)) as T;
    }
    return obj as T;
  }

  if (typeof obj !== 'object') {
    return obj as T;
  }

  const transformed: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(obj)) {
    // スキップするキーの場合はそのまま
    if (options.skipKeys?.includes(key)) {
      transformed[key] = value;
      continue;
    }

    const snakeKey = toSnakeCase(key);

    if (options.deep && value && typeof value === 'object') {
      transformed[snakeKey] = transformToSnakeCase(value, options);
    } else {
      transformed[snakeKey] = value;
    }
  }

  return transformed as T;
}

/**
 * API レスポンスを UI で使用可能な camelCase 形式に変換
 * @param response API からのレスポンスデータ
 * @param options 変換オプション
 * @returns camelCase に変換されたデータ
 */
export function transformApiResponse<T = Record<string, unknown>>(
  response: Record<string, unknown> | unknown[] | unknown,
  options?: CaseTransformerOptions
): T {
  return transformToCamelCase<T>(response, {
    deep: true,
    arrays: true,
    skipKeys: ['url', 'URL'], // URL 系は変換しない
    ...options,
  });
}

/**
 * UI データを API 送信用の snake_case 形式に変換
 * @param data UI からのデータ
 * @param options 変換オプション
 * @returns snake_case に変換されたデータ
 */
export function transformForApiRequest<T = Record<string, unknown>>(
  data: Record<string, unknown> | unknown[] | unknown,
  options?: CaseTransformerOptions
): T {
  return transformToSnakeCase<T>(data, {
    deep: true,
    arrays: true,
    skipKeys: ['url', 'URL'], // URL 系は変換しない
    ...options,
  });
}

/**
 * 特定のエンティティ用の変換関数
 */
export const EntityTransformers = {
  /**
   * 衣類アイテム用変換
   */
  clothingItem: (item: Record<string, unknown>) =>
    transformApiResponse(item, {
      skipKeys: ['url', 'URL', 'imageUrls', 'image_urls'],
    }),

  /**
   * 写真データ用変換
   */
  photo: (photo: Record<string, unknown>) =>
    transformApiResponse(photo, {
      skipKeys: ['url', 'URL', 'photoUrl', 'photo_url'],
    }),

  /**
   * コーディネート記録用変換
   */
  outfitRecord: (record: Record<string, unknown>) =>
    transformApiResponse(record),

  /**
   * AI 検出結果用変換
   */
  aiDetection: (detection: Record<string, unknown>) =>
    transformApiResponse(detection, {
      skipKeys: ['url', 'URL', 'annotatedImageUrl'],
    }),
};

/**
 * バッチ変換用ヘルパー
 */
export function transformBatch<T>(
  items: Record<string, unknown>[],
  transformer: (item: Record<string, unknown>) => T
): T[] {
  return items.map(transformer);
}
