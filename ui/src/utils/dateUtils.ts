import { format, parseISO } from 'date-fns';
import { ja } from 'date-fns/locale';
import { toZonedTime, fromZonedTime } from 'date-fns-tz';

const JST_TIMEZONE = 'Asia/Tokyo';

/**
 * JST（日本標準時）での日付処理を統一するユーティリティ
 *
 * 基本方針：
 * - UI表示は常にJST
 * - データベースはUTC保存
 * - API通信時にJST⇔UTC変換
 */
export const dateUtils = {
  /**
   * 日付をJSTでフォーマット
   * @param date Date オブジェクトまたはISO文字列
   * @param formatStr フォーマット文字列（デフォルト: 'yyyy-MM-dd HH:mm'）
   * @returns JSTでフォーマットされた文字列
   */
  formatJST: (
    date: Date | string,
    formatStr: string = 'yyyy-MM-dd HH:mm'
  ): string => {
    const dateObj = typeof date === 'string' ? parseISO(date) : date;
    const jstDate = toZonedTime(dateObj, JST_TIMEZONE);
    return format(jstDate, formatStr, { locale: ja });
  },

  /**
   * 日付をJSTで日本語フォーマット
   * @param date Date オブジェクトまたはISO文字列
   * @returns 日本語フォーマット（例: '2025 年 7 月 22 日（火）'）
   */
  formatJSTJapanese: (date: Date | string): string => {
    const dateObj = typeof date === 'string' ? parseISO(date) : date;
    const jstDate = toZonedTime(dateObj, JST_TIMEZONE);
    return format(jstDate, 'yyyy 年 M 月 d 日（E）', { locale: ja });
  },

  /**
   * JSTの日付をUTCに変換（API送信用）
   * @param jstDate JST基準のDateオブジェクト
   * @returns UTC基準のDateオブジェクト
   */
  jstToUTC: (jstDate: Date): Date => {
    return fromZonedTime(jstDate, JST_TIMEZONE);
  },

  /**
   * UTC日付をJST日付文字列に変換
   * @param utcDate UTC基準のDateオブジェクトまたはISO文字列
   * @returns YYYY-MM-DD形式のJST日付文字列
   */
  utcToJSTString: (utcDate: Date | string): string => {
    const dateObj = typeof utcDate === 'string' ? parseISO(utcDate) : utcDate;
    const jstDate = toZonedTime(dateObj, JST_TIMEZONE);
    return format(jstDate, 'yyyy-MM-dd');
  },

  /**
   * ISO文字列から日付部分を抽出（タイムゾーン考慮済）
   * @param isoString ISO文字列（例: 2025-07-17T12:00:00+09:00）
   * @returns YYYY-MM-DD形式の日付文字列
   */
  extractDateFromISO: (isoString: string): string => {
    try {
      const dateObj = parseISO(isoString);
      return format(dateObj, 'yyyy-MM-dd');
    } catch {
      // フォールバック：文字列から直接日付部分を抽出
      return isoString.split('T')[0];
    }
  },

  /**
   * JSTの日付をYYYY-MM-DD形式の文字列に変換（API送信用）
   * @param jstDate JST基準のDateオブジェクト
   * @returns YYYY-MM-DD形式の文字列
   */
  jstToDateString: (jstDate: Date): string => {
    const jstZoned = toZonedTime(jstDate, JST_TIMEZONE);
    return format(jstZoned, 'yyyy-MM-dd');
  },

  /**
   * 現在のJST時刻を取得
   * @returns JST基準の現在時刻
   */
  nowJST: (): Date => {
    return toZonedTime(new Date(), JST_TIMEZONE);
  },

  /**
   * JSTの今日の日付を YYYY-MM-DD 形式で取得
   * @returns 今日のJST日付文字列
   */
  todayJST: (): string => {
    return dateUtils.jstToDateString(dateUtils.nowJST());
  },

  /**
   * YYYY-MM-DD 文字列からJST正午のDateオブジェクトを作成
   * @param dateString YYYY-MM-DD形式の日付文字列
   * @returns JST正午のDateオブジェクト
   */
  parseDateAsJSTNoon: (dateString: string): Date => {
    const [year, month, day] = dateString.split('-').map(Number);
    const jstNoon = new Date(year, month - 1, day, 12, 0, 0, 0);
    return toZonedTime(jstNoon, JST_TIMEZONE);
  },

  /**
   * 日付が今日（JST）かどうかを判定
   * @param date 判定対象の日付
   * @returns 今日の場合true
   */
  isToday: (date: Date | string): boolean => {
    const targetDateString =
      typeof date === 'string' ? date : dateUtils.jstToDateString(date);
    return targetDateString === dateUtils.todayJST();
  },

  /**
   * 2つの日付が同じ日（JST）かどうかを判定
   * @param date1 比較対象の日付1
   * @param date2 比較対象の日付2
   * @returns 同じ日の場合true
   */
  isSameDay: (date1: Date | string, date2: Date | string): boolean => {
    const dateString1 =
      typeof date1 === 'string' ? date1 : dateUtils.jstToDateString(date1);
    const dateString2 =
      typeof date2 === 'string' ? date2 : dateUtils.jstToDateString(date2);
    return dateString1 === dateString2;
  },
};

/**
 * レガシー対応：既存コードとの互換性のため
 * @deprecated dateUtils.formatJST を使用してください
 */
export const formatDate = (date: Date | string, formatStr?: string) => {
  return dateUtils.formatJST(date, formatStr);
};

export default dateUtils;
