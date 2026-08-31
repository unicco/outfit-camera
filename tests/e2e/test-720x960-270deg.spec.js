const { test, expect } = require('@playwright/test');

test('720x960 + 反時計回り90度 最適化テスト', async ({ page }) => {
  // タッチスクリーン画面にアクセス
  await page.goto('http://pi-camera.local:3000/touchscreen');

  // ページの読み込み完了を待つ
  await page.waitForLoadState('networkidle');

  // 最適化設定でのスクリーンショットを撮影
  await page.screenshot({ path: 'stream-720x960-270deg-optimized.png', fullPage: true });

  // カメラ要素の情報を取得
  const cameraFeed = page.locator('img[alt*="Camera"]');
  await expect(cameraFeed.first()).toBeVisible({ timeout: 10000 });

  const cameraInfo = await cameraFeed.first().evaluate((el) => {
    const computed = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return {
      src: el.src,
      naturalWidth: el.naturalWidth,
      naturalHeight: el.naturalHeight,
      displayedWidth: rect.width,
      displayedHeight: rect.height,
      className: el.className,
      objectFit: computed.objectFit
    };
  });

  console.log('720x960 + 270度回転 最適化ストリーム情報:');
  console.log('Natural size:', `${cameraInfo.naturalWidth}x${cameraInfo.naturalHeight}`);
  console.log('Displayed size:', `${cameraInfo.displayedWidth}x${cameraInfo.displayedHeight}`);
  console.log('Object fit:', cameraInfo.objectFit);
  console.log('Full info:', JSON.stringify(cameraInfo, null, 2));

  console.log('720x960 + 反時計回り90度 最適化テスト完了');
});
