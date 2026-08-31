// Issue 260 対応: Playwright E2E テストグローバルセットアップ
// ブラウザリソース管理とメモリ最適化

const { chromium } = require('@playwright/test');

async function globalSetup() {
  console.log('🎭 Playwright Global Setup (Issue 260 対応)');

  // Issue 260 対応: 既存のブラウザプロセスクリーンアップ
  console.log('🧹 Cleaning up existing browser processes...');

  try {
    // 既存のChromiumプロセスを確認
    const { exec } = require('child_process');
    const { promisify } = require('util');
    const execAsync = promisify(exec);

    try {
      const { stdout } = await execAsync('timeout 5 pgrep -f "chrome|chromium|playwright" || true');
      if (stdout.trim()) {
        console.log(`⚠️  Found existing browser processes: ${stdout.trim()}`);
        // 既存プロセスは警告のみ、強制終了はしない（他のテストが実行中の可能性）
      } else {
        console.log('✅ No existing browser processes found');
      }
    } catch (error) {
      // pgrep コマンドが失敗またはタイムアウトしても継続
      console.log('ℹ️  Could not check for existing processes (timeout or command failed)');
    }

    // Issue 260 対応: テスト環境用最適化されたブラウザ起動確認
    console.log('🌐 Testing optimized browser launch...');

    const browser = await chromium.launch({
      headless: true,
      args: [
        '--max-old-space-size=256',      // Node.js ヒープサイズ制限
        '--memory-pressure-off',         // メモリプレッシャー無効化
        '--no-sandbox',                  // サンドボックス無効化
        '--disable-dev-shm-usage',       // /dev/shm 使用無効化
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding'
      ]
    });

    // 簡単な動作確認
    const context = await browser.newContext();
    const page = await context.newPage();

    // Issue 260 対応: about:blank 無限起動防止のため、data URL を使用
    try {
      await page.goto('data:text/html,<h1>Test Setup</h1>', {
        waitUntil: 'domcontentloaded',
        timeout: 5000
      });
      const title = await page.textContent('h1');

      if (title === 'Test Setup') {
        console.log('✅ Browser setup test passed');
      } else {
        console.log('⚠️  Browser setup test failed');
      }
    } catch (error) {
      console.log('⚠️  Browser navigation test failed, but continuing:', error.message);
    }

    // クリーンアップ
    await page.close();
    await context.close();
    await browser.close();

    console.log('🎯 Global setup completed successfully');

  } catch (error) {
    console.error('❌ Global setup failed:', error);
    throw error;
  }
}

module.exports = globalSetup;
