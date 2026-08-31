// Issue 260 対応: Playwright 設定最適化 - Chromium メモリ問題解決
// メモリ使用量削減とプロセス管理の最適化

module.exports = {
  testDir: './tests/e2e',
  testMatch: '**/*.spec.js',
  timeout: 30000,

  // Issue 260対応: グローバルセットアップ/ティアダウンでリソース管理
  globalSetup: require.resolve('./tests/e2e/global-setup.js'),
  globalTeardown: require.resolve('./tests/e2e/global-teardown.js'),

  // Issue 260対応: 並列実行数を制限してメモリ使用量削減
  workers: 1,  // 並列実行数を1に制限してメモリ使用量削減

  use: {
    // Issue 260対応: メモリ使用量削減のためヘッドレスモード
    headless: true,  // メモリ使用量削減のためヘッドレスモード
    viewport: { width: 480, height: 800 },
    screenshot: 'only-on-failure',

    // Issue 260対応: Chromium メモリ最適化オプション
    launchOptions: {
      args: [
        '--max-old-space-size=256',      // Node.js ヒープサイズ制限
        '--memory-pressure-off',         // メモリプレッシャー無効化
        '--no-sandbox',                  // サンドボックス無効化
        '--disable-dev-shm-usage',       // /dev/shm 使用無効化
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-extensions',
        '--disable-default-apps',
        '--disable-sync',
        '--disable-translate',
        '--disable-web-security',        // 開発環境のみ
        '--disable-features=TranslateUI,VizDisplayCompositor',
        '--process-per-site',           // プロセス分離最適化
        '--max_old_space_size=256'      // V8 メモリ制限
      ]
    }
  },

  // Issue 260対応: テストプロジェクト設定
  projects: [
    {
      name: 'chromium',
      use: {
        ...require('@playwright/test').devices['Desktop Chrome'],
        // Issue 260対応: デスクトップでも軽量設定
        viewport: { width: 1280, height: 720 }  // デフォルトより小さめ
      },
    },
  ],

  // Issue 260対応: レポート設定
  reporter: [
    ['list'],
    ['html', {
      outputFolder: 'test-results/html-report',
      open: 'never'  // メモリ使用量削減のため自動オープン無効
    }]
  ],

  // Issue 260対応: 出力ディレクトリ設定
  outputDir: 'test-results',

  // Issue 260対応: 再試行設定（メモリ問題によるフレークテスト対策）
  retries: process.env.CI ? 2 : 1,

  // Issue 260対応: テスト実行設定
  forbidOnly: !!process.env.CI,

  // Issue 260対応: Web サーバー設定（必要に応じて）
  webServer: {
    command: 'echo "Web server should be started separately"',
    port: 3000,
    reuseExistingServer: true,  // 既存のサーバーを再利用
  },
};
