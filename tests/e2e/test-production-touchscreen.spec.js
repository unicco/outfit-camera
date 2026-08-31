import { test, expect } from '@playwright/test';

test('production touchscreen display debug', async ({ page }) => {
  // Set viewport to match touchscreen dimensions
  await page.setViewportSize({ width: 480, height: 800 });

  // touchscreen本番環境にアクセス
  await page.goto('http://pi-camera.local:3000/touchscreen');

  // ページが読み込まれるまで待機
  await page.waitForTimeout(5000);

  // スクリーンショットを撮って表示状態を確認
  await page.screenshot({ path: 'production-touchscreen-debug.png', fullPage: true });

  // ストリーミング画像要素を探す
  const streamImages = await page.locator('img[alt*="Camera"]').all();

  for (let i = 0; i < streamImages.length; i++) {
    const img = streamImages[i];
    const boundingBox = await img.boundingBox();
    const src = await img.getAttribute('src');

    console.log(`Production Image ${i + 1}:`);
    console.log(`  src: ${src}`);
    console.log(`  dimensions: ${boundingBox?.width}x${boundingBox?.height}`);
    console.log(`  position: (${boundingBox?.x}, ${boundingBox?.y})`);

    // CSS スタイルを取得
    const styles = await img.evaluate((el) => {
      const computed = window.getComputedStyle(el);
      return {
        transform: el.style.transform || computed.transform,
        width: el.style.width || computed.width,
        height: el.style.height || computed.height,
        left: el.style.left || computed.left,
        top: el.style.top || computed.top,
        marginLeft: el.style.marginLeft || computed.marginLeft,
        marginTop: el.style.marginTop || computed.marginTop,
        objectFit: el.style.objectFit || computed.objectFit,
        position: el.style.position || computed.position
      };
    });

    console.log(`  CSS styles:`, styles);

    // natural dimensions を取得
    const naturalDimensions = await img.evaluate((el) => ({
      naturalWidth: el.naturalWidth,
      naturalHeight: el.naturalHeight,
      clientWidth: el.clientWidth,
      clientHeight: el.clientHeight
    }));

    console.log(`  natural: ${naturalDimensions.naturalWidth}x${naturalDimensions.naturalHeight}`);
    console.log(`  client: ${naturalDimensions.clientWidth}x${naturalDimensions.clientHeight}`);
  }

  // コンソールログを監視
  page.on('console', msg => {
    if (msg.text().includes('dimensions') || msg.text().includes('Stream') || msg.text().includes('Preview')) {
      console.log('Browser console:', msg.text());
    }
  });

  console.log('Production touchscreen page analyzed. Check production-touchscreen-debug.png for visual confirmation.');
});
