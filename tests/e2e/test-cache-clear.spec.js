const { test, expect } = require('@playwright/test');

test('タッチスクリーンキャッシュクリア検証', async ({ page, context }) => {
  // ブラウザキャッシュを全クリア
  await context.clearCookies();
  await context.clearPermissions();

  // タッチスクリーン画面にアクセス（強制リロード）
  await page.goto('http://pi-camera.local:3000/touchscreen', { waitUntil: 'networkidle' });

  // ハードリフレッシュ実行
  await page.keyboard.press('Control+F5');
  await page.waitForTimeout(3000);

  // 画面のスクリーンショットを撮影
  await page.screenshot({ path: 'touchscreen-cache-cleared.png', fullPage: true });

  // カメラ要素を確認
  const cameraFeed = page.locator('img[alt*="Camera"]');
  await expect(cameraFeed.first()).toBeVisible({ timeout: 10000 });

  // 現在の表示情報を取得
  const cameraInfo = await cameraFeed.first().evaluate((el) => {
    const computed = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return {
      className: el.className,
      computedStyles: {
        position: computed.position,
        left: computed.left,
        top: computed.top,
        width: computed.width,
        height: computed.height,
        transform: computed.transform,
        objectFit: computed.objectFit
      },
      boundingBox: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height
      },
      inlineStyles: el.style.cssText
    };
  });

  console.log('Cache cleared camera info:', JSON.stringify(cameraInfo, null, 2));
});
