// Issue 260 対応: Playwright E2E テストグローバルティアダウン
// テスト完了後のブラウザリソースクリーンアップ

async function globalTeardown() {
  console.log('🏁 Playwright Global Teardown (Issue 260 対応)');

  try {
    // Issue 260 対応: テスト完了後のブラウザプロセスクリーンアップ
    console.log('🧹 Cleaning up browser processes...');

    const { exec } = require('child_process');
    const { promisify } = require('util');
    const execAsync = promisify(exec);

    // 残存するブラウザプロセスを確認
    try {
      const { stdout } = await execAsync('pgrep -f "chrome|chromium" || true');
      if (stdout.trim()) {
        const processes = stdout.trim().split('\n');
        console.log(`🔍 Found ${processes.length} browser processes to clean up`);

        // 段階的クリーンアップ
        console.log('📤 Sending SIGTERM for graceful shutdown...');
        await execAsync('pkill -TERM -f "chrome|chromium" || true');

        // 3秒待機
        await new Promise(resolve => setTimeout(resolve, 3000));

        // まだ残っているプロセスを確認
        const { stdout: remaining } = await execAsync('pgrep -f "chrome|chromium" || true');
        if (remaining.trim()) {
          console.log('⚠️  Some processes still running, force killing...');
          await execAsync('pkill -KILL -f "chrome|chromium" || true');

          // 最終確認
          await new Promise(resolve => setTimeout(resolve, 1000));
          const { stdout: final } = await execAsync('pgrep -f "chrome|chromium" || true');
          if (final.trim()) {
            console.log('❌ Warning: Some browser processes may still be running');
          } else {
            console.log('✅ All browser processes cleaned up successfully');
          }
        } else {
          console.log('✅ All processes gracefully terminated');
        }
      } else {
        console.log('✅ No browser processes found to clean up');
      }
    } catch (error) {
      console.log('ℹ️  Could not perform process cleanup:', error.message);
    }

    // メモリ使用量の最終レポート
    try {
      const { stdout: memInfo } = await execAsync('ps aux | grep -E "(chrome|chromium)" | grep -v grep | wc -l || echo "0"');
      const processCount = parseInt(memInfo.trim());
      console.log(`📊 Final browser process count: ${processCount}`);
    } catch (error) {
      console.log('ℹ️  Could not get final process count');
    }

    console.log('🎯 Global teardown completed');

  } catch (error) {
    console.error('❌ Global teardown failed:', error);
    // ティアダウンの失敗はテストの失敗にしない
  }
}

module.exports = globalTeardown;
