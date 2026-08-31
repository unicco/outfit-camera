import { API_TIMEOUT } from '@/config/api';
import { API_URL } from '@/config/urls';
import { ApiClient } from '@/services/apiClient';

export interface UnifiedAnalysisRequest {
  photoId?: string;
  userId?: string;
  useFewShot?: boolean;
  returnEmbeddings?: boolean;
}

export interface UnifiedAnalysisResultItem {
  index: number;
  class: string;
  confidence: number;
  bbox: number[];
  item_type: string | null;
  item_type_confidence: number | null;
  combined_confidence?: number;
}

export interface UnifiedAnalysisResponse {
  photo_id?: string;
  segmentation: unknown[];
  item_types: unknown[];
  attributes: Record<string, unknown>;
  embeddings?: Record<number, number[]>;
  processing_time: {
    segmentation?: number;
    few_shot?: number;
    total: number;
  };
  unified_results: UnifiedAnalysisResultItem[];
}

export class UnifiedAnalysisService {
  private apiUrl: string;
  private client: ApiClient;

  constructor(apiUrl: string = API_URL) {
    this.apiUrl = apiUrl.replace(/\/$/, '');
    this.client = new ApiClient('');
  }

  private buildEndpoint(path: string): string {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;

    if (!this.apiUrl) {
      return normalizedPath;
    }

    const base = this.apiUrl;
    if (base.endsWith('/api') && normalizedPath.startsWith('/api/v2/')) {
      return `${base}${normalizedPath.slice(4)}`;
    }

    return `${base}${normalizedPath}`;
  }

  /**
   * 写真IDで統合分析を実行
   */
  async analyzePhoto(request: UnifiedAnalysisRequest): Promise<UnifiedAnalysisResponse> {
    return this.client.post<UnifiedAnalysisResponse>(
      this.buildEndpoint('/api/v2/unified/analyze'),
      {
        photo_id: request.photoId,
        user_id: request.userId,
        use_few_shot: request.useFewShot ?? true,
        return_embeddings: request.returnEmbeddings ?? false,
      },
      { timeout: API_TIMEOUT.AI_ANALYSIS }
    );
  }

  /**
   * 統合分析システムのステータスを取得
   */
  async getStatus(): Promise<{
    status: string;
    segmentation_method: string;
    use_few_shot: boolean;
    use_attribute_detector: boolean;
    components: {
      mobilesam: boolean;
      few_shot: boolean;
      attribute_detector: boolean;
    };
  }> {
    return this.client.get(
      this.buildEndpoint('/api/v2/unified/status')
    );
  }
}

// シングルトンインスタンス
export const unifiedAnalysisService = new UnifiedAnalysisService();
