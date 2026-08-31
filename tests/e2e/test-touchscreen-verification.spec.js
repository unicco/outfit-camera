const { test, expect } = require('@playwright/test');

test('タッチスクリーン画面の検証', async ({ page }) => {
  // タッチスクリーン画面にアクセス
  await page.goto('http://pi-camera.local:3000/touchscreen');

  // ページの読み込み完了を待つ
  await page.waitForLoadState('networkidle');

  // 画面のスクリーンショットを撮影
  await page.screenshot({ path: 'touchscreen-current-state.png', fullPage: true });

  // 基本要素の確認
  const cameraFeed = page.locator('[data-testid="camera-feed"], .camera-feed, img');
  await expect(cameraFeed.first()).toBeVisible({ timeout: 10000 });

  console.log('Camera feed element found');

  // 画像の実際のサイズと表示サイズを確認
  const cameraElement = await cameraFeed.first();
  const boundingBox = await cameraElement.boundingBox();
  console.log('Camera element bounding box:', boundingBox);

  // CSSスタイルを確認
  const styles = await cameraElement.evaluate((el) => {
    const computedStyle = window.getComputedStyle(el);
    return {
      objectFit: computedStyle.objectFit,
      objectPosition: computedStyle.objectPosition,
      width: computedStyle.width,
      height: computedStyle.height,
      transform: computedStyle.transform,
      maxWidth: computedStyle.maxWidth,
      maxHeight: computedStyle.maxHeight
    };
  });
  console.log('Camera element styles:', styles);

  // ページ全体のレイアウト確認
  const pageInfo = await page.evaluate(() => {
    return {
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      documentWidth: document.documentElement.scrollWidth,
      documentHeight: document.documentElement.scrollHeight
    };
  });
  console.log('Page layout info:', pageInfo);

  // 現在の問題を特定するため、詳細な情報を取得
  const detailedInfo = await page.evaluate(() => {
    const cameraElement = document.querySelector('[data-testid="camera-feed"], .camera-feed, img');
    if (cameraElement) {
      const rect = cameraElement.getBoundingClientRect();
      const computedStyle = window.getComputedStyle(cameraElement);
      return {
        element: cameraElement.tagName,
        className: cameraElement.className,
        src: cameraElement.src,
        naturalWidth: cameraElement.naturalWidth,
        naturalHeight: cameraElement.naturalHeight,
        displayedWidth: rect.width,
        displayedHeight: rect.height,
        position: {
          top: rect.top,
          left: rect.left,
          right: rect.right,
          bottom: rect.bottom
        },
        styles: {
          objectFit: computedStyle.objectFit,
          objectPosition: computedStyle.objectPosition,
          width: computedStyle.width,
          height: computedStyle.height,
          maxWidth: computedStyle.maxWidth,
          maxHeight: computedStyle.maxHeight,
          transform: computedStyle.transform,
          position: computedStyle.position,
          overflow: computedStyle.overflow
        }
      };
    }
    return null;
  });

  console.log('Detailed camera element info:', JSON.stringify(detailedInfo, null, 2));
});
