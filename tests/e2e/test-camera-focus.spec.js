const { test, expect } = require('@playwright/test');

test('カメラピント状況確認', async ({ page }) => {
  // タッチスクリーン画面にアクセス
  await page.goto('http://pi-camera.local:3000/touchscreen');

  // ページの読み込み完了を待つ
  await page.waitForLoadState('networkidle');

  // 現在のピント状況をスクリーンショット
  await page.screenshot({ path: 'camera-focus-current.png', fullPage: true });

  // カメラ要素の詳細情報を取得
  const cameraFeed = page.locator('img[alt*="Camera"]');
  await expect(cameraFeed.first()).toBeVisible({ timeout: 10000 });

  const imageDetails = await cameraFeed.first().evaluate((el) => {
    return {
      src: el.src,
      naturalWidth: el.naturalWidth,
      naturalHeight: el.naturalHeight,
      complete: el.complete,
      crossOrigin: el.crossOrigin
    };
  });

  console.log('カメラピント状況:');
  console.log('Image source:', imageDetails.src);
  console.log('Natural dimensions:', `${imageDetails.naturalWidth}x${imageDetails.naturalHeight}`);
  console.log('Image loaded:', imageDetails.complete);

  // 少し待ってから再度スクリーンショット（フォーカス確認用）
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'camera-focus-after-wait.png', fullPage: true });

  console.log('カメラピント状況確認完了 - スクリーンショットで画像品質を確認してください');
});
