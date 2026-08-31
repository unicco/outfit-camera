const { test, expect } = require('@playwright/test');

test('960x1280 + 反時計回り90度 テスト', async ({ page }) => {
  // タッチスクリーン画面にアクセス
  await page.goto('http://pi-camera.local:3000/touchscreen');

  // ページの読み込み完了を待つ
  await page.waitForLoadState('networkidle');

  // 新設定でのスクリーンショットを撮影
  await page.screenshot({ path: 'stream-960x1280-270deg.png', fullPage: true });

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

  console.log('960x1280 + 270度回転 ストリーム情報:');
  console.log('Natural size:', `${cameraInfo.naturalWidth}x${cameraInfo.naturalHeight}`);
  console.log('Displayed size:', `${cameraInfo.displayedWidth}x${cameraInfo.displayedHeight}`);
  console.log('Object fit:', cameraInfo.objectFit);
  console.log('Full info:', JSON.stringify(cameraInfo, null, 2));

  console.log('960x1280 + 反時計回り90度 テスト完了');
});
