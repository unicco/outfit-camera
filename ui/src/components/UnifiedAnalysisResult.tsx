import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, Shirt, Package } from 'lucide-react';

interface UnifiedResult {
  index: number;
  class: string;
  confidence: number;
  bbox: number[];
  item_type: string | null;
  item_type_confidence: number | null;
  combined_confidence?: number;
}

interface UnifiedAnalysisResultProps {
  isLoading: boolean;
  results?: {
    unified_results: UnifiedResult[];
    processing_time: {
      segmentation?: number;
      few_shot?: number;
      total: number;
    };
  };
}

export const UnifiedAnalysisResult: React.FC<UnifiedAnalysisResultProps> = ({
  isLoading,
  results
}) => {
  if (isLoading) {
    return (
      <Card className="w-full">
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
          <span className="ml-2 text-gray-500">MobileSAM で分析中...</span>
        </CardContent>
      </Card>
    );
  }

  if (!results || !results.unified_results || results.unified_results.length === 0) {
    return null;
  }

  const getItemTypeLabel = (itemType: string | null) => {
    const labels: Record<string, string> = {
      'tops': 'トップス',
      'bottoms': 'ボトムス',
      'dress': 'ワンピース',
      'outerwear': 'アウター',
      'accessories': 'アクセサリー'
    };
    return itemType ? labels[itemType] || itemType : '未分類';
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'bg-green-100 text-green-800';
    if (confidence >= 0.6) return 'bg-yellow-100 text-yellow-800';
    return 'bg-gray-100 text-gray-800';
  };

  // 安全性チェックを追加
  const unifiedResults = results.unified_results || [];
  const processingTime = results.processing_time || {};

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Package className="h-5 w-5" />
            統合分析結果
          </span>
          <span className="text-sm font-normal text-gray-500">
            処理時間: {processingTime.total?.toFixed(0) || 0}ms
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {unifiedResults.map((item, index) => (
            <div
              key={index}
              className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition-colors"
            >
              <div className="flex items-center gap-4">
                <div className="flex items-center justify-center w-12 h-12 bg-gray-100 rounded-full">
                  <Shirt className="h-6 w-6 text-gray-600" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">
                      {item.class.charAt(0).toUpperCase() + item.class.slice(1)}
                    </span>
                    <Badge
                      variant="secondary"
                      className={getConfidenceColor(item.confidence)}
                    >
                      {(item.confidence * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  {item.item_type && (
                    <div className="mt-1 flex items-center gap-2">
                      <span className="text-sm text-gray-600">→</span>
                      <span className="text-sm font-medium text-blue-600">
                        {getItemTypeLabel(item.item_type)}
                      </span>
                      {item.item_type_confidence && (
                        <Badge
                          variant="secondary"
                          className="text-xs bg-blue-50 text-blue-700"
                        >
                          {(item.item_type_confidence * 100).toFixed(0)}%
                        </Badge>
                      )}
                    </div>
                  )}
                </div>
              </div>
              {item.combined_confidence && (
                <div className="text-right">
                  <div className="text-xs text-gray-500">統合信頼度</div>
                  <div className="text-lg font-semibold text-gray-700">
                    {(item.combined_confidence * 100).toFixed(0)}%
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 処理時間の詳細 */}
        {Object.keys(processingTime).length > 0 && (
          <div className="mt-6 pt-4 border-t">
            <div className="text-sm text-gray-500">
              <div className="flex justify-between">
                <span>セグメンテーション (MobileSAM):</span>
                <span>
                  {processingTime.segmentation?.toFixed(0) || '-'}ms
                </span>
              </div>
              {processingTime.few_shot && (
                <div className="flex justify-between mt-1">
                  <span>アイテムタイプ検出 (Few-shot):</span>
                  <span>{processingTime.few_shot.toFixed(0)}ms</span>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
