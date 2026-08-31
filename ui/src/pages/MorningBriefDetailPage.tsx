import { useState, useEffect } from 'react';
import { apiClient } from '@/services/apiClient';
import { API_TIMEOUT } from '@/config/api';
import { logger } from '@/utils/logger';

// スマホ向けの今日のコーデ詳細ページ（/today）。
// HA push の clickAction の遷移先。CF Access 配下のブラウザから取得するので
// 認証はクッキー任せ。Pi 小画面（MorningBriefScreen）から分離した hero 大写真と
// 全構成アイテムをここで大きく見せる。
//
// apiClient がレスポンスを snake_case → camelCase に自動変換するため camelCase で受ける。
interface BriefItem {
  id: string;
  name: string;
  category: string;
  imageUrl: string | null;
}

interface BriefWeather {
  condition: string;
  temperature: number | null;
  tempMax: number | null;
  tempMin: number | null;
  precipitationMm: number;
  umbrellaRequired: boolean;
  available: boolean;
}

interface BriefHero {
  photoId: string;
  photoUrl: string | null;
  capturedDate: string | null;
  temperatureMax: number | null;
  temperatureMin: number | null;
  matchedByTemperature: boolean;
}

interface OutfitEntry {
  photoId: string;
  photoUrl: string | null;
  capturedDate: string | null;
  items: BriefItem[];
  meetTitle?: string | null;
}

interface AttendeeHistory {
  name: string;
  photos: OutfitEntry[];
}

interface BriefSchedule {
  attendees: string[];
  wornHistory: AttendeeHistory[];
}

interface MorningBrief {
  date: string;
  weather: BriefWeather;
  hero: BriefHero | null;
  items: BriefItem[];
  schedule: BriefSchedule;
}

const WEEKDAYS_JA = ['日', '月', '火', '水', '木', '金', '土'];

const WEATHER_MARK: Record<string, string> = {
  sunny: '☀️',
  cloudy: '☁️',
  rainy: '🌧️',
  snowy: '❄️',
};

// 天気ごとの配色（背景・枠線・アクセント文字）。Pi スタンバイ画面の配色と同系統で、
// 天気・傘・気温をまとめたバナーに使う。
const WEATHER_THEME: Record<
  string,
  { bg: string; border: string; accent: string }
> = {
  sunny: { bg: '#fff5e6', border: '#ffd9a8', accent: '#d97706' },
  cloudy: { bg: '#eef1f5', border: '#d3dae3', accent: '#475569' },
  rainy: { bg: '#e7f0fd', border: '#aecdf3', accent: '#2563eb' },
  snowy: { bg: '#f3f8fc', border: '#dbe7f2', accent: '#0ea5e9' },
};

const NEUTRAL_THEME = { bg: '#f1f5f9', border: '#e2e8f0', accent: '#475569' };

function dateParts(
  iso: string
): { year: number; month: number; day: number; weekday: string } | null {
  const [y, m, d] = iso.split('-').map(n => parseInt(n, 10));
  if (!y || !m || !d) {
    return null;
  }
  const weekday = WEEKDAYS_JA[new Date(y, m - 1, d).getDay()] ?? '';
  return { year: y, month: m, day: d, weekday };
}

// ヒーローキャプション用のフル日付: 「2026 年 3 月 27 日（金）」
function formatFullDate(iso: string): string {
  const p = dateParts(iso);
  return p ? `${p.year} 年 ${p.month} 月 ${p.day} 日（${p.weekday}）` : '';
}

// 人別セクションの相対日付: 「10 日前」「3 か月前」「1 年前」。狭いカードで折り返さない
// よう短く出す。基準日は brief.date（サーバの JST 今日）でテストも決定的になる。
function formatRelative(iso: string, todayIso: string): string {
  const p = dateParts(iso);
  const t = dateParts(todayIso);
  if (!p || !t) {
    return '';
  }
  const from = new Date(p.year, p.month - 1, p.day);
  const to = new Date(t.year, t.month - 1, t.day);
  const days = Math.round((to.getTime() - from.getTime()) / 86_400_000);
  if (days < 0) {
    return ''; // 未来日（通常は起きない・past のみ）
  }
  if (days === 0) {
    return '今日';
  }
  if (days < 30) {
    return `${days} 日前`;
  }
  const months = Math.floor(days / 30);
  if (months < 12) {
    return `${months} か月前`;
  }
  return `${Math.floor(months / 12)} 年前`;
}

function formatTemp(value: number | null): string {
  return value === null || value === undefined ? '--' : `${Math.round(value)}°`;
}

export function MorningBriefDetailPage() {
  const [brief, setBrief] = useState<MorningBrief | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  // 人別コーデ（ICS フェッチ ~4 秒）は本体と分けて遅延ロードする（#463 体感速度改善）。
  const [wornHistory, setWornHistory] = useState<AttendeeHistory[]>([]);
  const [scheduleLoading, setScheduleLoading] = useState(true);
  // 原本が GCS から失われた写真の記録が DB に残り得るので、読めなかった画像は
  // 壊れアイコンでなく欠損表示に落とす。キーは hero / 各写真 ID。
  const [imageErrors, setImageErrors] = useState<Record<string, boolean>>({});

  const markImageError = (key: string) => {
    setImageErrors(prev => ({ ...prev, [key]: true }));
  };

  useEffect(() => {
    let cancelled = false;

    // 本体（天気・ヒーロー・構成アイテム）= ICS 不要で速い。先に出す。
    const fetchBrief = async () => {
      try {
        const data = await apiClient.get<MorningBrief>(
          '/api/v2/morning-brief?schedule=skip',
          { timeout: API_TIMEOUT.MORNING_BRIEF }
        );
        if (!cancelled) {
          setBrief(data);
          setHasError(false);
        }
      } catch (error) {
        logger.warn(
          'Could not fetch morning brief:',
          error instanceof Error ? error.message : error
        );
        if (!cancelled) {
          setHasError(true);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    // 人別コーデ = ICS が要る重い部分。後追いで差し込む（失敗してもページは成立）。
    const fetchSchedule = async () => {
      try {
        const data = await apiClient.get<BriefSchedule>(
          '/api/v2/morning-brief/schedule',
          { timeout: API_TIMEOUT.MORNING_BRIEF }
        );
        if (!cancelled) {
          setWornHistory(data.wornHistory ?? []);
        }
      } catch (error) {
        logger.warn(
          'Could not fetch morning brief schedule:',
          error instanceof Error ? error.message : error
        );
      } finally {
        if (!cancelled) {
          setScheduleLoading(false);
        }
      }
    };

    fetchBrief();
    fetchSchedule();
    return () => {
      cancelled = true;
    };
  }, []);

  const weather = brief?.weather;
  const hero = brief?.hero ?? null;
  const items = brief?.items ?? [];
  const today = brief ? dateParts(brief.date) : null;
  const umbrellaRequired = weather?.umbrellaRequired ?? false;
  const weatherMark =
    weather && weather.available
      ? WEATHER_MARK[weather.condition] ?? '☁️'
      : '–';
  const weatherTheme =
    weather && weather.available
      ? WEATHER_THEME[weather.condition] ?? NEUTRAL_THEME
      : NEUTRAL_THEME;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-md px-5 py-6">
        {/* ヘッダ: 今日の日付（月・日を大きく・曜日は続けて 1 行） */}
        {today && (
          <div className="font-extrabold leading-tight">
            <span className="text-5xl">{today.month}</span>
            <span className="text-xl"> 月 </span>
            <span className="text-5xl">{today.day}</span>
            <span className="text-xl"> 日</span>
            <span className="text-xl font-bold text-slate-400">
              {' '}
              {today.weekday}曜
            </span>
          </div>
        )}

        {/* 天気・傘・気温まとめバナー（天気で配色） */}
        <div
          className="mt-4 flex items-center gap-4 rounded-2xl border px-5 py-4"
          style={{ background: weatherTheme.bg, borderColor: weatherTheme.border }}
        >
          <div className="text-5xl leading-none">{weatherMark}</div>
          <div className="leading-tight">
            <div className="text-sm font-bold text-slate-500">傘</div>
            <div
              className="text-2xl font-black"
              style={{ color: weatherTheme.accent }}
            >
              {umbrellaRequired ? 'いる' : 'いらない'}
            </div>
            <div className="mt-1 text-sm font-bold text-slate-500">
              最高 {formatTemp(weather?.tempMax ?? null)} 最低{' '}
              {formatTemp(weather?.tempMin ?? null)}
            </div>
          </div>
        </div>

        {/* hero コーデ大写真 */}
        <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white">
          {/* overflow-hidden 必須: ぼかし背景の scale(1.25) が下のキャプションに
              はみ出して文字を覆い隠すのを防ぐ（#463） */}
          <div className="relative aspect-[3/4] overflow-hidden bg-neutral-800">
            {hero?.photoUrl && !imageErrors.hero ? (
              <>
                <div
                  className="absolute inset-0"
                  style={{
                    backgroundImage: `url(${hero.photoUrl})`,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                    filter: 'blur(28px) saturate(1.1)',
                    transform: 'scale(1.25)',
                  }}
                />
                <div className="absolute inset-0 flex items-center justify-center">
                  <img
                    src={hero.photoUrl}
                    alt="コーディネート例"
                    className="max-h-full max-w-full object-contain"
                    onError={() => markImageError('hero')}
                  />
                </div>
              </>
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-white/70">
                {isLoading
                  ? '読み込み中…'
                  : hasError
                    ? 'コーデを取得できませんでした'
                    : hero
                      ? '写真を表示できませんでした'
                      : 'コーデ記録がまだありません'}
              </div>
            )}
          </div>
          {hero?.capturedDate && (
            <div className="px-4 py-2 text-right text-xs font-bold text-slate-600">
              {hero.matchedByTemperature
                ? '気温が近い日の記録から · '
                : '直近の記録から · '}
              {formatFullDate(hero.capturedDate)}
            </div>
          )}
        </div>

        {/* 構成アイテム（全件） */}
        {items.length > 0 && (
          <div className="mt-5">
            <div className="mb-2 text-sm font-bold text-slate-500">構成アイテム</div>
            <div className="grid grid-cols-3 gap-3">
              {items.map(item => (
                <div key={item.id}>
                  <div className="aspect-square overflow-hidden rounded-xl border border-slate-200 bg-white">
                    {item.imageUrl && !imageErrors[item.id] ? (
                      <img
                        src={item.imageUrl}
                        alt={item.name}
                        className="h-full w-full object-contain"
                        onError={() => markImageError(item.id)}
                      />
                    ) : (
                      <div className="h-full w-full bg-slate-100" />
                    )}
                  </div>
                  <div className="mt-1 truncate text-center text-xs font-bold text-slate-500">
                    {item.name}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 今日会う人のコーデは ICS フェッチが要るので遅延ロード中の合図を出す。
            本体エラー時は出さない（schedule が遅れて返っても人別欄を出さない） */}
        {!hasError && scheduleLoading && wornHistory.length === 0 && (
          <div className="mt-6 text-center text-xs text-slate-400">
            今日会う人のコーデを読み込み中…
          </div>
        )}

        {/* 今日会う人ごとの過去コーデ（着衣被り回避）。
            各人「○○ と会った時」の全身写真を日付付きで並べる。記録が無い人は空表示。 */}
        {!hasError && wornHistory.length > 0 && (
          <div className="mt-6 space-y-5">
            {wornHistory.map(person => (
              <div key={person.name}>
                <div className="mb-2 text-sm font-bold text-slate-500">
                  {person.name} と会った時
                </div>
                {person.photos.length > 0 ? (
                  <div className="flex gap-3 overflow-x-auto pb-1">
                    {person.photos.map(entry => (
                      <div key={entry.photoId} className="w-32 shrink-0">
                        <div className="aspect-[3/4] overflow-hidden rounded-xl border border-slate-200 bg-neutral-800">
                          {entry.photoUrl && !imageErrors[entry.photoId] ? (
                            <img
                              src={entry.photoUrl}
                              alt={`${person.name} と会った時のコーデ`}
                              className="h-full w-full object-cover"
                              onError={() => markImageError(entry.photoId)}
                            />
                          ) : (
                            <div className="h-full w-full bg-slate-100" />
                          )}
                        </div>
                        <div className="mt-1 text-center text-xs font-bold text-slate-500">
                          {entry.capturedDate && brief
                            ? formatRelative(entry.capturedDate, brief.date)
                            : ''}
                        </div>
                        {entry.meetTitle && (
                          <div className="truncate text-center text-xs text-slate-400">
                            {entry.meetTitle}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-200 px-4 py-3 text-center text-xs text-slate-400">
                    まだ記録がありません
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
