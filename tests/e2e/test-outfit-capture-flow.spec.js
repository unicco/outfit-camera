import { test, expect } from '@playwright/test';

test.describe('Outfit Capture Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Start at the capture screen
    await page.goto('http://localhost:5173/capture');
  });

  test('complete outfit capture workflow', async ({ page }) => {
    // 1. Verify initial capture screen
    await expect(page.locator('h1')).toContainText('今日のコーデを撮影');

    // 2. Check camera stream is visible
    const cameraView = page.locator('img[alt="Camera view"]');
    await expect(cameraView).toBeVisible();

    // 3. Click capture button
    const captureButton = page.getByRole('button', { name: /今日のコーデを撮影/ });
    await expect(captureButton).toBeVisible();
    await captureButton.click();

    // 4. Wait for photo to be taken (simulate camera delay)
    await page.waitForTimeout(1000);

    // 5. Verify preview screen appears
    await expect(page.locator('text=撮影完了')).toBeVisible({ timeout: 10000 });

    // 6. Check that clothing items are detected
    const clothingItems = page.locator('[data-testid="detected-clothing-item"]');
    await expect(clothingItems.first()).toBeVisible({ timeout: 5000 }); // At least one item detected

    // 7. Click save button
    const saveButton = page.getByRole('button', { name: /保存/ });
    await saveButton.click();

    // 8. Verify navigation to outfit history
    await expect(page).toHaveURL(/\/outfits/, { timeout: 5000 });

    // 9. Verify the new outfit appears in history
    const todayOutfit = page.locator('[data-testid="outfit-card"]').first();
    await expect(todayOutfit).toBeVisible();
  });

  test('manual clothing selection', async ({ page }) => {
    // Navigate to wardrobe
    await page.goto('http://localhost:5173/wardrobe');

    // Wait for items to load
    await page.waitForSelector('[data-testid="clothing-grid-item"]', { timeout: 10000 });

    // Select multiple items
    const items = page.locator('[data-testid="clothing-grid-item"]');
    const itemCount = await items.count();

    if (itemCount >= 2) {
      // Click first two items
      await items.nth(0).click();
      await items.nth(1).click();

      // Verify selection indicators
      await expect(items.nth(0)).toHaveClass(/selected/);
      await expect(items.nth(1)).toHaveClass(/selected/);

      // Create outfit from selection
      const createOutfitButton = page.getByRole('button', { name: /コーディネートを作成/ });
      await expect(createOutfitButton).toBeVisible();
      await createOutfitButton.click();

      // Verify outfit creation success
      await expect(page.locator('text=コーディネートを作成しました')).toBeVisible();
    }
  });

  test('view outfit details', async ({ page }) => {
    // Navigate to outfit history
    await page.goto('http://localhost:5173/outfits');

    // Wait for outfits to load
    await page.waitForSelector('[data-testid="outfit-card"]', { timeout: 10000 });

    // Click on first outfit
    const firstOutfit = page.locator('[data-testid="outfit-card"]').first();
    await firstOutfit.click();

    // Verify outfit detail view
    await expect(page.locator('[data-testid="outfit-detail"]')).toBeVisible();

    // Check clothing items are displayed
    const detailItems = page.locator('[data-testid="outfit-detail-item"]');
    await expect(detailItems.first()).toBeVisible(); // At least one item

    // Verify item information
    const firstItem = detailItems.first();
    await expect(firstItem.locator('img')).toBeVisible();
    await expect(firstItem.locator('[data-testid="item-name"]')).toBeVisible();
    await expect(firstItem.locator('[data-testid="item-category"]')).toBeVisible();
  });

  test('touchscreen mode capture', async ({ page }) => {
    // Navigate to touchscreen mode
    await page.goto('http://localhost:5173/touchscreen');

    // Verify standby screen
    await expect(page.locator('text=タッチして撮影開始')).toBeVisible();

    // Touch to start (simulate touch event)
    await page.locator('body').click();

    // Verify countdown
    await expect(page.locator('[data-testid="countdown"]')).toBeVisible();

    // Wait for countdown to complete
    await page.waitForTimeout(3500);

    // Verify capture complete
    await expect(page.locator('text=撮影完了')).toBeVisible({ timeout: 10000 });

    // Return to standby
    await page.waitForTimeout(5000);
    await expect(page.locator('text=タッチして撮影開始')).toBeVisible();
  });

  test('wardrobe item upload', async ({ page }) => {
    // Navigate to wardrobe
    await page.goto('http://localhost:5173/wardrobe');

    // Click add item button
    const addButton = page.getByRole('button', { name: /アイテムを追加/ });
    await addButton.click();

    // Fill in item details
    await page.fill('[name="name"]', 'Test Shirt');
    await page.selectOption('[name="category"]', 'tops');
    await page.fill('[name="brand"]', 'Test Brand');

    // Upload image (simulate file selection)
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'test-shirt.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from('fake-image-data')
    });

    // Submit form
    const submitButton = page.getByRole('button', { name: /登録/ });
    await submitButton.click();

    // Verify success message
    await expect(page.locator('text=アイテムを登録しました')).toBeVisible({ timeout: 10000 });

    // Verify item appears in grid
    await expect(page.locator('text=Test Shirt')).toBeVisible();
  });
});
