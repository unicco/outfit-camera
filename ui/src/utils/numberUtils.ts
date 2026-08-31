/**
 * 数値処理・フォーマットユーティリティ関数
 */

/**
 * 数値を指定した小数点以下の桁数で丸める
 * @param num 対象数値
 * @param decimals 小数点以下の桁数
 * @returns 丸められた数値
 */
export const round = (num: number, decimals: number = 0): number => {
  const factor = Math.pow(10, decimals);
  return Math.round(num * factor) / factor;
};

/**
 * 数値を3桁区切りでフォーマットする
 * 注意: 整数を前提。小数を渡すと小数部にも区切りが入るため、
 * 非整数は呼び出し側で round / Math.round してから渡すこと
 * @param num 対象数値
 * @param separator 区切り文字（デフォルト: ','）
 * @returns フォーマットされた文字列
 */
export const formatNumber = (num: number, separator: string = ','): string => {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, separator);
};

/**
 * 数値を通貨形式でフォーマットする
 * @param num 対象数値
 * @param currency 通貨記号（デフォルト: '¥'）
 * @param decimals 小数点以下の桁数（デフォルト: 0）
 * @returns フォーマットされた通貨文字列
 */
export const formatCurrency = (
  num: number,
  currency: string = '¥',
  decimals: number = 0
): string => {
  const rounded = round(num, decimals);
  const formatted = formatNumber(rounded);
  return `${currency}${formatted}`;
};

/**
 * 数値をパーセンテージ形式でフォーマットする
 * 0-1 の割合と 0-100 のパーセント値の両方を受け付ける
 * @param value 対象値（0-1 の割合、または 0-100 のパーセント値）
 * @returns パーセンテージ文字列（無効値は 'N/A'）
 */
export const formatPercent = (value?: number): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  const percent = value <= 1 ? value * 100 : value;
  return `${percent.toFixed(1)}%`;
};

/**
 * ファイルサイズを人間が読みやすい形式でフォーマットする
 * @param bytes バイト数
 * @param decimals 小数点以下の桁数（デフォルト: 2）
 * @returns フォーマットされたファイルサイズ
 */
export const formatFileSize = (bytes: number, decimals: number = 2): string => {
  if (bytes === 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${round(bytes / Math.pow(k, i), decimals)} ${units[i]}`;
};
