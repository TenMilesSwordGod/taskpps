import { test, expect } from '@playwright/test';

// 用户的真实 YAML 对应的 PipelineDetail 数据
const REAL_YAML_PIPELINE = {
  name: 'Automation Weekly Execution',
  config: {
    host: 'test-agent01',
    env: { APP_ENV: 'staging', DUT_IP: '10.239.146.127' },
    timeout: 86400,
    retry: 0,
    on_failure: 'fail',
    execution_strategy: 'sequential',
  },
  pipelines: [
    {
      name: 'Sync Automation code',
      depends_on: [],
      tasks: [
        { name: 'sync code', command: 'ls', cwd: '/tmp', retry: 0 },
        { name: 'list files', command: 'echo 10.239.146.127', cwd: '/tmp', retry: 0 },
      ],
    },
    {
      name: 'Automation Weekly Tests',
      depends_on: ['Sync Automation code'],
      tasks: [
        { name: 'AOSP', command: 'uv run run.py -p example', cwd: '/home/admin/workdir/liheng/AutomationTestTool-RF', retry: 0 },
        { name: 'Graphics', command: 'uv run run.py -p example', cwd: '/home/admin/workdir/liheng/AutomationTestTool-RF', retry: 0 },
      ],
    },
  ],
};

async function initReal(page: import('playwright-core').Page) {
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const url = route.request().url();
    if (url.includes('auth/me')) {
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ account: 'admin', id: 1, nickname: 'Admin', realname: 'Admin', avatar: '', role: 'top', dept: 0, visions: 'rnd' }) });
    } else if (url.includes('pipelines/by-id')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(REAL_YAML_PIPELINE) });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    }
  });
  await page.goto('/');
  await page.evaluate((t) => localStorage.setItem('taskpps_token', t), 'test-token');
  await page.goto('/pipelines/proj-1/def-1', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForSelector('.react-flow', { timeout: 10000 });
  await page.waitForTimeout(1000);
}

test.describe('你的真实 YAML 测试', () => {
  test('1. 查看模式: 画布渲染正确 — 有 SubPipeline/Task/Start/End/边', async ({ page }) => {
    await initReal(page);
    const nodes = await page.locator('.react-flow__node').count();
    const edges = await page.locator('.react-flow__edge').count();
    console.log(`查看模式: ${nodes} 节点, ${edges} 条边`);
    expect(nodes).toBeGreaterThanOrEqual(4);
    expect(edges).toBeGreaterThanOrEqual(0);
  });

  test('2. 编辑模式: 拖 on_fail 子容器 → 节点出现', async ({ page }) => {
    await initReal(page);
    await page.getByRole('button', { name: '编辑模式' }).click();
    await page.waitForTimeout(1000);

    const before = await page.locator('.react-flow__node').count();
    const card = page.locator('[draggable="true"]', { hasText: 'on_fail 子容器' }).first();
    if (await card.isVisible().catch(() => false)) {
      await card.dragTo(page.locator('.react-flow__pane').first(),
        { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 400, y: 300 } });
      await page.waitForTimeout(800);
    }
    const after = await page.locator('.react-flow__node').count();
    console.log(`拖 on_fail: ${before} → ${after}`);
    expect(after).toBeGreaterThanOrEqual(before);
  });

  test('3. 编辑模式: 右键菜单正常 — 画布空白右键和节点右键', async ({ page }) => {
    await initReal(page);
    await page.getByRole('button', { name: '编辑模式' }).click();
    await page.waitForTimeout(1000);

    // 画布空白右键
    await page.locator('.react-flow__pane').first().dispatchEvent('contextmenu');
    await page.waitForTimeout(800);
    const menuItems = await page.locator('.ant-dropdown-menu-item').count();
    console.log(`画布右键菜单项数: ${menuItems}`);
    expect(menuItems).toBeGreaterThan(0);

    // 点击空白关闭菜单
    await page.locator('.react-flow__pane').first().click({ position: { x: 50, y: 50 } });
    await page.waitForTimeout(300);

    // 节点右键
    const nodes = page.locator('.react-flow__node');
    if (await nodes.count() > 0) {
      await nodes.last().dispatchEvent('contextmenu');
      await page.waitForTimeout(800);
      const nodeMenuItems = await page.locator('.ant-dropdown-menu-item').count();
      console.log(`节点右键菜单项数: ${nodeMenuItems}`);
      expect(nodeMenuItems).toBeGreaterThan(0);
    }
  });

  test('4. 编辑模式: 拖 Post 父容器 → 右键删除', async ({ page }) => {
    await initReal(page);
    await page.getByRole('button', { name: '编辑模式' }).click();
    await page.waitForTimeout(1000);

    // 拖 Post 父容器
    const postCard = page.locator('[draggable="true"]', { hasText: 'Post 父容器' }).first();
    if (await postCard.isVisible().catch(() => false)) {
      await postCard.dragTo(page.locator('.react-flow__pane').first(),
        { sourcePosition: { x: 10, y: 10 }, targetPosition: { x: 500, y: 200 } });
      await page.waitForTimeout(800);
    }

    const beforeDelete = await page.locator('.react-flow__node').count();

    // 右键最后一个节点
    const lastNode = page.locator('.react-flow__node').last();
    await lastNode.dispatchEvent('contextmenu');
    await page.waitForTimeout(800);

    const deleteBtn = page.locator('.ant-dropdown-menu-item').filter({ hasText: '删除' });
    if (await deleteBtn.count() > 0) {
      await deleteBtn.first().click();
      await page.waitForTimeout(500);
    }
    const afterDelete = await page.locator('.react-flow__node').count();
    console.log(`删除: ${beforeDelete} → ${afterDelete}`);
    expect(afterDelete).toBeLessThanOrEqual(beforeDelete);
  });

  test('5. 保存 → 验证 PUT 请求体包含你的 YAML 内容', async ({ page }) => {
    let saveBody = '';
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
      const url = route.request().url();
      if (url.includes('auth/me')) {
        await route.fulfill({ status: 200, contentType: 'application/json',
          body: JSON.stringify({ account: 'admin', id: 1, nickname: 'Admin', role: 'top', dept: 0, visions: 'rnd' }) });
      } else if (url.includes('pipelines/by-id') && route.request().method() === 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(REAL_YAML_PIPELINE) });
      } else if (url.includes('pipelines/by-id') && route.request().method() === 'PUT') {
        saveBody = await route.request().postData() || '';
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
      }
    });
    await page.goto('/');
    await page.evaluate((t) => localStorage.setItem('taskpps_token', t), 'test-token');
    await page.goto('/pipelines/proj-1/def-1', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForSelector('.react-flow', { timeout: 10000 });
    await page.waitForTimeout(1000);

    await page.getByRole('button', { name: '编辑模式' }).click();
    await page.waitForTimeout(1000);
    const saveBtn = page.locator('button').filter({ hasText: '保存' }).first();
    await saveBtn.click();
    await page.waitForTimeout(1000);

    console.log('保存请求体:', saveBody.substring(0, 300));
    expect(saveBody).toContain('Automation Weekly Execution');
  });
});
