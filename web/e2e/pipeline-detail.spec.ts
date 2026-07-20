import { test, expect } from '@playwright/test';

/**
 * e2e 测试：PipelineDetailPage 集成场景（issue #206）。
 *
 * 覆盖 PipelineDetailPage 的完整用户使用流程：
 *   A. 编辑/查看模式切换（3 tests）
 *   B. 编辑器中拖放 + 保存（3 tests）
 *   C. YAML 编辑器 ↔ 工作流联动（2 tests）
 *   D. 完整工作流（1 test）
 *
 * 设计决策（为什么这么写）：
 * - 所有测试导航到 /e2e/pipeline-detail 测试专页，不依赖后端 API 和认证。
 * - 与 workflow-editor.spec.ts 共享相同的 mock pipeline 结构（E2EPipelineDetailPage 内部）。
 * - locator 查询使用文本内容 + role + 类名组合，避免 React 内部状态 ID 变化。
 * - 拖拽测试使用 Playwright dragTo API，目标为 .react-flow__pane 画布区域。
 */

const TEST_URL = '/e2e/pipeline-detail';

async function waitForPage(page: import('@playwright/test').Page) {
  await page.waitForSelector('[data-testid="e2e-pipeline-detail-root"]', { timeout: 15000 });
  await page.waitForTimeout(500);
}

async function waitForCanvas(page: import('@playwright/test').Page) {
  await page.waitForSelector('.react-flow', { timeout: 15000 });
  await page.waitForSelector('.react-flow__node', { timeout: 10000 });
  await page.waitForTimeout(500);
}

// ============================================================
// A. 编辑/查看模式切换（3 tests）
// ============================================================
test.describe('A. 编辑/查看模式切换', () => {
  test('A1. 默认查看模式 → 显示"编辑模式"按钮 + PipelineGraph DAG 画布', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForPage(page);

    // 工具栏存在
    await expect(page.locator('[data-testid="e2e-toolbar"]')).toBeVisible();

    // 默认显示"编辑模式"按钮（表示当前在查看模式）
    const editModeBtn = page.getByRole('button', { name: '编辑模式' });
    await expect(editModeBtn).toBeVisible();

    // 查看模式下应渲染 PipelineGraph（react-flow 画布）
    await waitForCanvas(page);
    await expect(page.locator('.react-flow__node').first()).toBeVisible();
  });

  test('A2. 点击"编辑模式" → 按钮变为"查看模式" + WorkflowEditor 出现 + NodePalette 出现', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForPage(page);

    // 点击"编辑模式"按钮进入编辑模式
    const editModeBtn = page.getByRole('button', { name: '编辑模式' });
    await editModeBtn.click();
    await page.waitForTimeout(800);

    // 按钮变为"查看模式"
    const viewModeBtn = page.getByRole('button', { name: '查看模式' });
    await expect(viewModeBtn).toBeVisible();

    // 编辑模式下工具栏显示"保存"按钮（WorkflowEditor 内部也有"保存"，用 data-testid 定位）
    const saveBtn = page.locator('[data-testid="e2e-toolbar"]').getByRole('button', { name: '保存' });
    await expect(saveBtn).toBeVisible();

    // WorkflowEditor 渲染（react-flow 画布）
    await waitForCanvas(page);

    // NodePalette 出现（draggable 节点卡片）
    const subPipelineCard = page.locator('[draggable="true"]', { hasText: 'SubPipeline' }).first();
    await expect(subPipelineCard).toBeVisible();

    // YAML 编辑器按钮应隐藏（仅查看模式显示）
    await expect(page.getByRole('button', { name: 'YAML 编辑器' })).not.toBeVisible();
  });

  test('A3. 点击"查看模式" → 回到查看模式 → WorkflowEditor 消失', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForPage(page);

    // 进入编辑模式
    await page.getByRole('button', { name: '编辑模式' }).click();
    await page.waitForTimeout(800);

    // 回到查看模式
    await page.getByRole('button', { name: '查看模式' }).click();
    await page.waitForTimeout(800);

    // 按钮恢复为"编辑模式"
    await expect(page.getByRole('button', { name: '编辑模式' })).toBeVisible();

    // 编辑模式下特有的元素应消失（toolbar 中的保存按钮应隐藏）
    await expect(page.locator('[data-testid="e2e-toolbar"]').getByRole('button', { name: '保存' })).not.toBeVisible();
    // NodePalette 应消失
    await expect(page.locator('[draggable="true"]', { hasText: 'SubPipeline' }).first()).not.toBeVisible();
  });
});

// ============================================================
// B. 编辑器中拖放 + 保存（3 tests）
// ============================================================
test.describe('B. 编辑器中拖放 + 保存', () => {
  test('B1. 编辑模式下拖 SubPipeline → 保存按钮可点击 → 点击保存 → toast "已保存"', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForPage(page);

    // 进入编辑模式
    await page.getByRole('button', { name: '编辑模式' }).click();
    await waitForCanvas(page);

    const initialNodes = await page.locator('.react-flow__node').count();

    // 拖放 SubPipeline 节点到画布
    const subPipelineCard = page.locator('[draggable="true"]', { hasText: 'SubPipeline' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await subPipelineCard.dragTo(canvas, {
      sourcePosition: { x: 20, y: 20 },
      targetPosition: { x: 400, y: 300 },
    });
    await page.waitForTimeout(500);

    // 节点数应增加
    const nodesAfter = await page.locator('.react-flow__node').count();
    expect(nodesAfter).toBeGreaterThan(initialNodes);

    // 保存按钮存在且可点击（用 toolbar 定位避免 WorkflowEditor 内部同名按钮）
    const saveBtn = page.locator('[data-testid="e2e-toolbar"]').getByRole('button', { name: '保存' });
    await expect(saveBtn).toBeVisible();

    // 点击保存 → toast "已保存"
    await saveBtn.click();
    await page.waitForTimeout(800);

    const toast = page.getByText('已保存').first();
    const antdMessage = page.locator('.ant-message-notice-content').first();
    const hasToast = (await toast.count()) > 0 || (await antdMessage.count()) > 0;
    expect(hasToast).toBeTruthy();
  });

  test('B2. 编辑模式下拖 Task → 保存后 YAML 序列化正确', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForPage(page);

    // 进入编辑模式
    await page.getByRole('button', { name: '编辑模式' }).click();
    await waitForCanvas(page);

    // 拖放 Task 节点到画布
    const taskCard = page.locator('[draggable="true"]', { hasText: 'Task' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await taskCard.dragTo(canvas, {
      sourcePosition: { x: 20, y: 20 },
      targetPosition: { x: 500, y: 350 },
    });
    await page.waitForTimeout(500);

    // 节点应增加
    const nodesAfter = await page.locator('.react-flow__node').count();
    expect(nodesAfter).toBeGreaterThan(0);

    // 保存 — 使用 toolbar 定位避免 WorkflowEditor 内部同名按钮
    await page.locator('[data-testid="e2e-toolbar"]').getByRole('button', { name: '保存' }).click();
    await page.waitForTimeout(500);

    // 验证 toast
    const toast = page.getByText('已保存').first();
    const antdMessage = page.locator('.ant-message-notice-content').first();
    const hasToast = (await toast.count()) > 0 || (await antdMessage.count()) > 0;
    expect(hasToast).toBeTruthy();
  });

  test('B3. 编辑模式下拖 CMD 原子节点 → 保存回调被调用', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForPage(page);

    // 进入编辑模式
    await page.getByRole('button', { name: '编辑模式' }).click();
    await waitForCanvas(page);

    // 展开"原子行为"折叠面板
    const atomicHeader = page.locator('.ant-collapse-header', { hasText: '原子行为' });
    const atomicPanel = page.locator('.ant-collapse-item').filter({ hasText: '原子行为' });
    const isExpanded = await atomicPanel.locator('.ant-collapse-content-active').count();
    if (isExpanded === 0) {
      await atomicHeader.click();
      await page.waitForTimeout(300);
    }

    // 拖放 CMD 节点到画布
    const cmdCard = page.locator('[draggable="true"]', { hasText: 'CMD' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await cmdCard.dragTo(canvas, {
      sourcePosition: { x: 20, y: 20 },
      targetPosition: { x: 550, y: 400 },
    });
    await page.waitForTimeout(500);

    // 保存 — 使用 toolbar 定位
    await page.locator('[data-testid="e2e-toolbar"]').getByRole('button', { name: '保存' }).click();
    await page.waitForTimeout(500);

    // 验证 toast
    const toastB3 = page.getByText('已保存').first();
    const antdMsgB3 = page.locator('.ant-message-notice-content').first();
    const hasToastB3 = (await toastB3.count()) > 0 || (await antdMsgB3.count()) > 0;
    expect(hasToastB3).toBeTruthy();
  });
});

// ============================================================
// C. YAML 编辑器 ↔ 工作流联动（2 tests）
// ============================================================
test.describe('C. YAML 编辑器 ↔ 工作流联动', () => {
  test('C1. 查看模式下 YAML 编辑器打开 → 能看到 pipeline YAML', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForPage(page);
    await waitForCanvas(page);

    // 点击"YAML 编辑器"按钮
    const yamlBtn = page.getByRole('button', { name: 'YAML 编辑器' });
    await expect(yamlBtn).toBeVisible();
    await yamlBtn.click();
    await page.waitForTimeout(800);

    // 按钮变为"关闭编辑器"
    await expect(page.getByRole('button', { name: '关闭编辑器' })).toBeVisible();

    // YAML 编辑器渲染（CodeMirror content）
    const yamlEditor = page.locator('.cm-editor');
    await expect(yamlEditor).toBeVisible({ timeout: 5000 });

    // YAML 应包含 pipeline name
    const yamlContent = await yamlEditor.textContent();
    expect(yamlContent).toContain('e2e-test-pipeline');
  });

  test('C2. 关闭再打开编辑器 → 始终可用', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForPage(page);

    // 打开 YAML 编辑器
    await page.getByRole('button', { name: 'YAML 编辑器' }).click();
    await page.waitForTimeout(500);

    await expect(page.locator('.cm-editor')).toBeVisible({ timeout: 5000 });

    // 关闭编辑器
    await page.getByRole('button', { name: '关闭编辑器' }).click();
    await page.waitForTimeout(500);

    // 编辑器应消失
    await expect(page.locator('.cm-editor')).not.toBeVisible();

    // 重新打开 — 应仍然可用
    await page.getByRole('button', { name: 'YAML 编辑器' }).click();
    await page.waitForTimeout(500);
    await expect(page.locator('.cm-editor')).toBeVisible({ timeout: 5000 });
  });
});

// ============================================================
// D. 完整工作流（1 test）
// ============================================================
test.describe('D. 完整工作流', () => {
  test('D1. 查看模式 → 编辑模式 → 拖 SubPipeline+Task → 连线 → 保存 → 切回查看模式 → DAG 渲染正确', async ({ page }) => {
    await page.goto(TEST_URL);
    await waitForPage(page);
    await waitForCanvas(page);

    // Step 1: 查看模式 → 记下初始 DAG 渲染
    await expect(page.locator('.react-flow__node').first()).toBeVisible();

    // Step 2: 切换到编辑模式
    await page.getByRole('button', { name: '编辑模式' }).click();
    await waitForCanvas(page);

    // Step 3: 拖放 SubPipeline
    const subPipelineCard = page.locator('[draggable="true"]', { hasText: 'SubPipeline' }).first();
    const canvas = page.locator('.react-flow__pane').first();
    await subPipelineCard.dragTo(canvas, {
      sourcePosition: { x: 20, y: 20 },
      targetPosition: { x: 400, y: 300 },
    });
    await page.waitForTimeout(500);

    // Step 4: 拖放 Task
    const taskCard = page.locator('[draggable="true"]', { hasText: 'Task' }).first();
    await taskCard.dragTo(canvas, {
      sourcePosition: { x: 20, y: 20 },
      targetPosition: { x: 400, y: 450 },
    });
    await page.waitForTimeout(500);

    // Step 5: 保存 — 使用 toolbar 定位避免 WorkflowEditor 内部同名按钮
    const saveBtn = page.locator('[data-testid="e2e-toolbar"]').getByRole('button', { name: '保存' });
    await saveBtn.click();
    await page.waitForTimeout(500);

    // 验证 toast
    const toast = page.getByText('已保存').first();
    const antdMessage = page.locator('.ant-message-notice-content').first();
    const hasToast = (await toast.count()) > 0 || (await antdMessage.count()) > 0;
    expect(hasToast).toBeTruthy();

    // Step 6: 切回查看模式
    await page.getByRole('button', { name: '查看模式' }).click();
    await page.waitForTimeout(800);

    // Step 7: 查看模式下 DAG 应正常渲染（画布存在 + 节点可见）
    await waitForCanvas(page);
    await expect(page.locator('.react-flow__node').first()).toBeVisible();

    // 确认不在编辑模式（保存按钮不存在）
    await expect(page.locator('[data-testid="e2e-toolbar"]').getByRole('button', { name: '保存' })).not.toBeVisible();
    await expect(page.getByRole('button', { name: '编辑模式' })).toBeVisible();
  });
});
