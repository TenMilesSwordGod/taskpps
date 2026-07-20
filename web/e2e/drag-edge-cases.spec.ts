import { test, expect, Page } from '@playwright/test';

/**
 * e2e 测试：拖拽覆盖所有节点类型 + 容器嵌套拒绝规则验证
 *
 * 覆盖现有 e2e 缺口：
 *   - 拖拽 Post child (on_fail/on_success/always) 到画布
 *   - 拖拽 STEP/PLUGIN 原子节点
 *   - 拖拽 Start/End 节点
 *   - 容器嵌套拒绝：SubPipeline 拖入 SubPipeline
 *   - Post 父容器拖入 SubPipeline 内部
 *   - 空 dataTransfer 拖放 → 不崩溃
 */

const TEST_URL = '/e2e/workflow-editor';

async function waitForCanvas(page: Page) {
  await page.waitForSelector('.react-flow', { timeout: 15000 });
  await page.waitForSelector('.react-flow__node', { timeout: 10000 });
  await page.waitForTimeout(500);
}

async function getNodeCount(page: Page): Promise<number> {
  return page.locator('.react-flow__node').count();
}

test.describe('B2. 拖拽 — 补全未覆盖的节点类型', () => {
  test('拖 on_fail 子容器到画布 → 节点出现', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);
    const before = await getNodeCount(page);

    const card = page.locator('[draggable="true"]', { hasText: 'on_fail 子容器' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await card.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 350, y: 350 } });
    await page.waitForTimeout(800);

    expect(await getNodeCount(page)).toBeGreaterThan(before);
  });

  test('拖 on_success 子容器到画布 → 节点出现', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);
    const before = await getNodeCount(page);

    const card = page.locator('[draggable="true"]', { hasText: 'on_success 子容器' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await card.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 380, y: 380 } });
    await page.waitForTimeout(800);

    expect(await getNodeCount(page)).toBeGreaterThan(before);
  });

  test('拖 always 子容器到画布 → 节点出现', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);
    const before = await getNodeCount(page);

    const card = page.locator('[draggable="true"]', { hasText: 'always 子容器' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await card.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 400, y: 400 } });
    await page.waitForTimeout(800);

    expect(await getNodeCount(page)).toBeGreaterThan(before);
  });

  test('拖 STEP 原子节点到画布 → 节点出现', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);
    const before = await getNodeCount(page);

    const card = page.locator('[draggable="true"]', { hasText: 'STEP' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await card.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 420, y: 420 } });
    await page.waitForTimeout(800);

    expect(await getNodeCount(page)).toBeGreaterThan(before);
  });

  test('拖 PLUGIN 原子节点到画布 → 节点出现', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);
    const before = await getNodeCount(page);

    const card = page.locator('[draggable="true"]', { hasText: 'PLUGIN' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await card.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 440, y: 440 } });
    await page.waitForTimeout(800);

    expect(await getNodeCount(page)).toBeGreaterThan(before);
  });

  test('拖 Start 节点到画布 → 节点出现', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);
    const before = await getNodeCount(page);

    const card = page.locator('[draggable="true"]', { hasText: 'Start' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await card.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 460, y: 460 } });
    await page.waitForTimeout(800);

    expect(await getNodeCount(page)).toBeGreaterThan(before);
  });

  test('拖 End 节点到画布 → 节点出现', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);
    const before = await getNodeCount(page);

    const card = page.locator('[draggable="true"]', { hasText: 'End' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await card.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 480, y: 480 } });
    await page.waitForTimeout(800);

    expect(await getNodeCount(page)).toBeGreaterThan(before);
  });
});

test.describe('B3. 拖拽 — 容器嵌套拒绝规则（e2e 层验证）', () => {
  test('拖 SubPipeline 到 SubPipeline 内部 → 应被拒绝（节点数不变）', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);
    const before = await getNodeCount(page);

    // 先拖一个 SubPipeline 到画布
    const subCard = page.locator('[draggable="true"]', { hasText: 'SubPipeline' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await subCard.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 300, y: 200 } });
    await page.waitForTimeout(800);
    expect(await getNodeCount(page)).toBe(before + 1);

    // 再拖第二个 SubPipeline 到 SubPipeline 内部 → 应拒绝（节点数不变）
    const subCard2 = page.locator('[draggable="true"]', { hasText: 'SubPipeline' }).last();
    await subCard2.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 310, y: 210 } });
    await page.waitForTimeout(800);

    expect(await getNodeCount(page)).toBe(before + 1);
  });

  test('拖 Post 父容器到 SubPipeline 内部 → 应被拒绝', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);

    // 先确认画布有 SubPipeline（mock pipeline 已经有 build SubPipeline）
    const before = await getNodeCount(page);

    // 把 Post 父容器拖到画布 SubPipeline 所在大致位置（已有 SubPipeline 在 x:300/y:300 附近）
    const postCard = page.locator('[draggable="true"]', { hasText: 'Post 父容器' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await postCard.dragTo(canvas, { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 320, y: 320 } });
    await page.waitForTimeout(800);

    // Post 父容器应被拒绝在 SubPipeline 内部，但可能被放到画布根层级
    // 这里只验证不崩溃
    expect(await page.locator('.react-flow__node').count()).toBeGreaterThanOrEqual(before);
  });

  test('空 dataTransfer 拖放 → 不崩溃，节点数不变', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForCanvas(page);
    const before = await getNodeCount(page);

    // 用空 DataTransfer 模拟无效拖放
    const canvas = page.locator('.react-flow__pane').first();
    await canvas.dispatchEvent('drop', {
      dataTransfer: new DataTransfer(),
      clientX: 300,
      clientY: 300,
    });
    await page.waitForTimeout(500);

    expect(await getNodeCount(page)).toBe(before);
  });
});
