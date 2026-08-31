const { test, expect } = require('@playwright/test');

test('90度回転ストリームテスト', async ({ page }) => {
  // タッチスクリーン画面にアクセス
  await page.goto('http://pi-camera.local:3000/touchscreen');

  // ページの読み込み完了を待つ
  await page.waitForLoadState('networkidle');

  // 90度回転後のスクリーンショットを撮影
  await page.screenshot({ path: 'rotated-stream-test.png', fullPage: true });

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

  console.log('90度回転ストリーム情報:', JSON.stringify(cameraInfo, null, 2));

  // ストリーム自体にアクセスして直接確認
  const streamResponse = await page.request.get('http://pi-camera.local:8001/stream');
  console.log('Stream response status:', streamResponse.status());
  console.log('Stream response headers:', Object.fromEntries(streamResponse.headers()));

  console.log('90度回転ストリームテスト完了');
});
