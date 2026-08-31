const isDevelopment = import.meta.env.DEV
const isProduction = import.meta.env.PROD

// ログレベルの定義
enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  NONE = 4
}

// 環境に応じたログレベルの設定
const currentLogLevel = isProduction ? LogLevel.ERROR : LogLevel.DEBUG

class Logger {
  private shouldLog(level: LogLevel): boolean {
    return level >= currentLogLevel
  }

  debug(...args: unknown[]): void {
    if (this.shouldLog(LogLevel.DEBUG)) {
      console.log(...args)
    }
  }

  info(...args: unknown[]): void {
    if (this.shouldLog(LogLevel.INFO)) {
      console.info(...args)
    }
  }

  warn(...args: unknown[]): void {
    if (this.shouldLog(LogLevel.WARN)) {
      console.warn(...args)
    }
  }

  error(...args: unknown[]): void {
    if (this.shouldLog(LogLevel.ERROR)) {
      console.error(...args)
    }
  }

  // 開発時のみ実行されるログ
  dev(...args: unknown[]): void {
    if (isDevelopment) {
      console.log('[DEV]', ...args)
    }
  }

  // テーブル表示（開発時のみ）
  table(data: unknown): void {
    if (isDevelopment && console.table) {
      console.table(data)
    }
  }

  // グループ化（開発時のみ）
  group(label: string): void {
    if (isDevelopment && console.group) {
      console.group(label)
    }
  }

  groupEnd(): void {
    if (isDevelopment && console.groupEnd) {
      console.groupEnd()
    }
  }

  // 実行時間計測（開発時のみ）
  time(label: string): void {
    if (isDevelopment && console.time) {
      console.time(label)
    }
  }

  timeEnd(label: string): void {
    if (isDevelopment && console.timeEnd) {
      console.timeEnd(label)
    }
  }
}

export const logger = new Logger()

// 既存のコードとの互換性のための名前付きエクスポート
export const log = logger
