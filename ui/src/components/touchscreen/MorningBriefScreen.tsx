import React, { useState, useEffect } from 'react';
import { Camera } from 'lucide-react';
import { apiClient } from '@/services/apiClient';
import { API_TIMEOUT } from '@/config/api';
import { logger } from '@/utils/logger';

// apiClient がレスポンスを snake_case → camelCase に自動変換するため camelCase で受ける。
// 玄関の Pi は離れて一瞬見るだけなので、傘の要否と天気だけを背景色とアイコンで伝える。
// 最高気温やコーデ詳細はスマホ詳細ページ（/today）と HA push が持つ。
interface BriefWeather {
  condition: string;
  umbrellaRequired: boolean;
  available: boolean;
}

interface MorningBrief {
  weather: BriefWeather;
}

interface MorningBriefScreenProps {
  onCaptureStart: () => void;
  onReloadTouchscreen?: () => void;
}

// 天気アイコン（タイルに敷き詰める絵柄）。傘がいる日は傘で埋める。
const CONDITION_MARK: Record<string, string> = {
  sunny: '☀️',
  cloudy: '☁️',
  rainy: '🌧️',
  snowy: '❄️',
};

// 遠目でも一目で判別できるよう、天気ごとに彩度の高い別系統の色にする
// （晴れ=赤系 / 曇り=グレー系 / 雨=青系 / 雪=白系）。パステルだと離れると見分けが
// つかないので、はっきり違う色相・濃さにしている。
const CONDITION_BG: Record<string, string> = {
  sunny: 'linear-gradient(180deg,#ff7a59 0%,#e0342b 100%)',
  cloudy: 'linear-gradient(180deg,#aeb7c4 0%,#6d7889 100%)',
  rainy: 'linear-gradient(180deg,#4d90e0 0%,#1f4fa8 100%)',
  snowy: 'linear-gradient(180deg,#eef6ff 0%,#cfe2f5 100%)',
};

// 天気不明のときの背景。曇りの濃いグレーと紛れないよう、あえて淡く平板なグレーにする。
const NEUTRAL_BG = 'linear-gradient(180deg,#eef1f5 0%,#e3e8ef 100%)';

// 480px 程度の縦長画面を埋めるタイル数（72px 角想定）。均一に敷くので並びは固定。
const TILE_COUNT = 84;

export const MorningBriefScreen: React.FC<MorningBriefScreenProps> = ({
  onCaptureStart,
  onReloadTouchscreen,
}) => {
  const [brief, setBrief] = useState<MorningBrief | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetchBrief = async () => {
      try {
        // Pi 画面は天気しか使わないので schedule（ICS フェッチ ~4 秒）は省く
        const data = await apiClient.get<MorningBrief>(
          '/api/v2/morning-brief?schedule=skip',
          { timeout: API_TIMEOUT.MORNING_BRIEF }
        );
        if (!cancelled) {
          setBrief(data);
        }
      } catch (error) {
        // 取得失敗でも撮影は使えるべきなので、画面は描画を続ける（brief=null のまま）
        logger.warn(
          'Could not fetch morning brief (non-critical):',
          error instanceof Error ? error.message : error
        );
      }
    };

    fetchBrief();

    // 天気の更新のため 30 分ごと、復帰時に取り直す
    const interval = setInterval(fetchBrief, 30 * 60 * 1000);
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        fetchBrief();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, []);

  const weather = brief?.weather;
  const weatherKnown = weather?.available ?? false;
  const condition = weather?.condition ?? '';
  const umbrellaRequired = weatherKnown && (weather?.umbrellaRequired ?? false);

  // 傘がいる日は傘で埋める。それ以外は天気の絵柄で埋める。
  const tileMark = umbrellaRequired
    ? '☂️'
    : (CONDITION_MARK[condition] ?? '☁️');
  const background = weatherKnown
    ? (umbrellaRequired
        ? CONDITION_BG.rainy // 傘がいる日は雨想定で青背景
        : CONDITION_BG[condition] ?? NEUTRAL_BG)
    : NEUTRAL_BG;

  return (
    <div
      className="h-full relative overflow-hidden"
      style={{ background }}
    >
      {onReloadTouchscreen && (
        <button
          type="button"
          aria-label="タッチスクリーンをリロードする"
          onClick={onReloadTouchscreen}
          className="absolute top-4 right-4 z-20 px-3 py-1 rounded-full border border-black/10 text-[11px] font-medium text-slate-500 bg-white/60 backdrop-blur-sm"
        >
          RESET
        </button>
      )}

      {/* 天気アイコンのタイル壁紙。天気不明のときは敷かず無地グレーのまま */}
      {weatherKnown && (
        <div
          aria-hidden
          className="absolute inset-0 flex flex-wrap content-center justify-center gap-x-3 gap-y-2 px-2"
          style={{ opacity: 0.55 }}
        >
          {Array.from({ length: TILE_COUNT }).map((_, i) => (
            <span key={i} style={{ fontSize: 56, lineHeight: 1 }}>
              {tileMark}
            </span>
          ))}
        </div>
      )}

      {/* 中央を持ち上げてボタンを際立たせるソフトグロー */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(circle at 50% 46%, rgba(255,255,255,.55) 0%, rgba(255,255,255,0) 46%)',
        }}
      />

      {/* 中央のでかい撮影ボタン */}
      <div className="relative h-full flex items-center justify-center z-10">
        <button
          type="button"
          onClick={onCaptureStart}
          className="relative group"
          style={{ touchAction: 'manipulation' }}
          aria-label="撮影する"
        >
          <div className="w-64 h-64 rounded-full bg-[#1f2733] flex flex-col items-center justify-center shadow-2xl transition-all duration-200 group-active:scale-95 group-active:shadow-lg">
            <Camera className="w-28 h-28 text-white" strokeWidth={1.75} />
            <span className="mt-2 text-white font-extrabold" style={{ fontSize: 28, letterSpacing: 4 }}>
              撮影
            </span>
          </div>
          <div className="absolute inset-0 rounded-full bg-black/20 animate-ping" />
        </button>
      </div>
    </div>
  );
};
