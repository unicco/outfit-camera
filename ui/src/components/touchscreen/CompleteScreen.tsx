import React from 'react';
import { CheckCircle } from 'lucide-react';

export const CompleteScreen: React.FC = () => {
  return (
    <div className="h-full flex items-center justify-center bg-gradient-to-br from-green-50 to-emerald-100">
      <div className="text-center">
        <div className="inline-flex items-center justify-center w-32 h-32 rounded-full bg-green-500 mb-8">
          <CheckCircle className="w-20 h-20 text-white" />
        </div>
        <h1 className="text-4xl font-bold text-gray-800 mb-4">記録完了！</h1>
        <p className="text-xl text-gray-600">
          今日のコーディネートを記録しました
        </p>
      </div>
    </div>
  );
};
