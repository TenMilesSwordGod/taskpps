import { test, expect, Page } from '@playwright/test';

const TEST_URL = '/e2e/workflow-editor';

async function waitForCanvas(page: Page) {
  await page.waitForSelector('.react-flow', { timeout: 10000 });
  await page.waitForTimeout(800);
}

test.describe('Keyboard Delete', () => {
  test('drag CMD → click select → press Delete key → node disappears', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);

    const before = await page.locator('.react-flow__node').count();

    // drag CMD from palette
    const cmdCard = page.locator('[draggable="true"]', { hasText: 'CMD' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await cmdCard.dragTo(canvas, {
      sourcePosition: { x: 10, y: 10 },
      targetPosition: { x: 300, y: 300 },
    });
    await page.waitForTimeout(800);
    expect(await page.locator('.react-flow__node').count()).toBeGreaterThan(before);

    // click the new node to select it — force:true 绕过容器重叠
    const newNode = page.locator('.react-flow__node').last();
    await newNode.click({ force: true });
    await page.waitForTimeout(400);

    // press Delete key
    await page.keyboard.press('Delete');
    await page.waitForTimeout(500);

    expect(await page.locator('.react-flow__node').count()).toBe(before);
  });

  test('drag CMD → click select → press Backspace → node disappears', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);

    const before = await page.locator('.react-flow__node').count();

    const cmdCard = page.locator('[draggable="true"]', { hasText: 'CMD' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await cmdCard.dragTo(canvas, {
      sourcePosition: { x: 10, y: 10 },
      targetPosition: { x: 300, y: 300 },
    });
    await page.waitForTimeout(800);

    const newNode = page.locator('.react-flow__node').last();
    await newNode.click({ force: true });
    await page.waitForTimeout(400);

    await page.keyboard.press('Backspace');
    await page.waitForTimeout(500);

    expect(await page.locator('.react-flow__node').count()).toBe(before);
  });

  test('Delete key does NOT remove start/end/pipeline sentinel nodes', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);

    const before = await page.locator('.react-flow__node').count();

    // try clicking __start__ node
    const startNode = page.locator('.react-flow__node').first();
    await startNode.click({ force: true });
    await page.waitForTimeout(400);
    await page.keyboard.press('Delete');
    await page.waitForTimeout(400);

    expect(await page.locator('.react-flow__node').count()).toBe(before);
  });
});
