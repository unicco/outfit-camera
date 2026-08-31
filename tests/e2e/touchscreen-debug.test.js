import { test, expect } from '@playwright/test';

test('touchscreen streaming display debug', async ({ page }) => {
  // Set viewport to match touchscreen dimensions
  await page.setViewportSize({ width: 480, height: 800 });

  // touchscreenページにアクセス
  await page.goto('http://localhost:3000/touchscreen');

  // ページが読み込まれるまで待機
  await page.waitForTimeout(5000);

  // スクリーンショットを撮って表示状態を確認
  await page.screenshot({ path: 'touchscreen-debug.png', fullPage: true });

  // ストリーミング画像要素を探す
  const streamImages = await page.locator('img[alt*="Camera"]').all();

  for (let i = 0; i < streamImages.length; i++) {
    const img = streamImages[i];
    const boundingBox = await img.boundingBox();
    const src = await img.getAttribute('src');

    console.log(`Image ${i + 1}:`);
    console.log(`  src: ${src}`);
    console.log(`  dimensions: ${boundingBox?.width}x${boundingBox?.height}`);
    console.log(`  position: (${boundingBox?.x}, ${boundingBox?.y})`);

    // natural dimensions を取得
    const naturalDimensions = await img.evaluate((el) => ({
      naturalWidth: el.naturalWidth,
      naturalHeight: el.naturalHeight,
      clientWidth: el.clientWidth,
      clientHeight: el.clientHeight,
      style: {
        transform: el.style.transform,
        objectFit: el.style.objectFit || window.getComputedStyle(el).objectFit
      }
    }));

    console.log(`  natural: ${naturalDimensions.naturalWidth}x${naturalDimensions.naturalHeight}`);
    console.log(`  client: ${naturalDimensions.clientWidth}x${naturalDimensions.clientHeight}`);
    console.log(`  transform: ${naturalDimensions.style.transform}`);
    console.log(`  objectFit: ${naturalDimensions.style.objectFit}`);
  }

  // コンソールログを取得
  page.on('console', msg => {
    if (msg.text().includes('dimensions') || msg.text().includes('Stream') || msg.text().includes('Preview')) {
      console.log('Browser console:', msg.text());
    }
  });

  // タッチスクリーンの現在の状態を確認
  const currentScreen = await page.locator('[data-testid="current-screen"], .h-full').first().screenshot();

  console.log('Touchscreen page analyzed. Check touchscreen-debug.png for visual confirmation.');
});
