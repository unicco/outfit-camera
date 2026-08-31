const { test, expect } = require('@playwright/test');

test('解像度修正後の撮影テスト', async ({ page }) => {
  // タッチスクリーン画面にアクセス
  await page.goto('http://pi-camera.local:3000/touchscreen');

  // ページの読み込み完了を待つ
  await page.waitForLoadState('networkidle');

  // まずプレビュー画面のスクリーンショットを撮影
  await page.screenshot({ path: 'preview-before-capture.png', fullPage: true });

  // 撮影ボタンをクリック
  const captureButton = page.locator('button').filter({ hasText: '撮影' }).or(
    page.locator('.w-64.h-64') // カメラアイコンボタン
  );

  await captureButton.first().click();

  // カウントダウン画面を待つ
  await page.waitForTimeout(8000); // 7秒カウントダウン + バッファ

  // プレビュー画面になるまで待つ
  const saveButton = page.locator('button').filter({ hasText: '保存' });
  await expect(saveButton).toBeVisible({ timeout: 10000 });

  // 撮影結果のスクリーンショットを撮影
  await page.screenshot({ path: 'capture-result.png', fullPage: true });

  // 撮影された画像の情報を取得
  const capturedImage = page.locator('img').filter({ hasNot: page.locator('[alt*="Camera"]') });

  const imageInfo = await capturedImage.first().evaluate((el) => {
    return {
      src: el.src,
      naturalWidth: el.naturalWidth,
      naturalHeight: el.naturalHeight,
      className: el.className
    };
  });

  console.log('Captured image info:', imageInfo);

  // 保存をクリック
  await saveButton.click();

  // 完了画面を待つ
  await page.waitForTimeout(3000);

  console.log('Resolution fix test completed');
});
