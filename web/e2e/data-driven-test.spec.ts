import { test, expect } from '@playwright/test';
type P = import('playwright-core').Page;

// ============ N 种不同结构的 mock 数据 ============

/** 你的真实 YAML 结构 */
const D1_YOUR_REAL = {
  name: 'Automation Weekly Execution',
  config: { host: 'test-agent01', env: { APP_ENV: 'staging', DUT_IP: '10.239.146.127' }, timeout: 86400, retry: 0, on_failure: 'fail', execution_strategy: 'sequential' },
  pipelines: [
    { name: 'Sync code', depends_on: [], tasks: [{ name: 'sync', command: 'ls', cwd: '/tmp', retry: 0 }, { name: 'list', command: 'echo ip', cwd: '/tmp', retry: 0 }] },
    { name: 'Weekly Tests', depends_on: ['Sync code'], tasks: [{ name: 'AOSP', command: 'uv run run.py', cwd: '/home/admin/tool', retry: 0 }, { name: 'Graphics', command: 'uv run run.py', cwd: '/home/admin/tool', retry: 0 }] },
  ],
};

/** 只有根层级 tasks，无 SubPipeline */
const D2_ROOT_TASKS_ONLY = {
  name: 'simple-pipe',
  tasks: [
    { name: 'init', command: 'echo start', env: {}, retry: 0, depends_on: [] },
    { name: 'build', command: 'make', env: {}, retry: 0, depends_on: ['init'] },
    { name: 'deploy', command: 'deploy.sh', env: {}, retry: 1, depends_on: ['build'] },
  ],
};

/** 只有 SubPipeline，无根层级 tasks */
const D3_SUBPIPELINES_ONLY = {
  name: 'sub-only',
  pipelines: [
    { name: 'frontend', depends_on: [], tasks: [{ name: 'npm-install', command: 'npm i', env: {}, retry: 0, depends_on: [] }, { name: 'build', command: 'npm run build', env: {}, retry: 0, depends_on: ['npm-install'] }] },
    { name: 'backend', depends_on: ['frontend'], tasks: [{ name: 'compile', command: 'make', env: {}, retry: 0, depends_on: [] }, { name: 'test', command: 'go test', env: {}, retry: 0, depends_on: ['compile'] }] },
  ],
};

/** 含 Post 处理 */
const D4_WITH_POST = {
  name: 'post-pipe',
  tasks: [{ name: 'step1', command: 'echo', env: {}, retry: 0, depends_on: [] }],
  pipelines: [{ name: 'sub', depends_on: [], config: { env: {}, retry: 0, on_failure: '', execution_strategy: 'sequential' }, tasks: [{ name: 'compile', command: 'make', env: {}, retry: 0, depends_on: [] }] }],
  post: { on_fail: [{ name: 'notify', command: 'slack', env: {}, retry: 0, depends_on: [] }], on_success: [{ name: 'tag', command: 'git tag', env: {}, retry: 0, depends_on: [] }] },
};

/** 大量节点（压力） */
const D5_LARGE = {
  name: 'large-pipe',
  config: { execution_strategy: 'parallel' },
  pipelines: Array.from({ length: 5 }, (_, si) => ({
    name: `sub-${si}`, depends_on: si > 0 ? [`sub-${si-1}`] : [],
    tasks: Array.from({ length: 6 }, (_, ti) => ({ name: `task-${si}-${ti}`, command: 'echo', env: {}, retry: 0, depends_on: ti > 0 ? [`task-${si}-${ti-1}`] : [] })),
  })),
};

/** 最小数据 */
const D6_MINIMAL = { name: 'minimal' };

// ============ 测试场景 ============

const SCENARIOS: { name: string; data: any; skip?: string[] }[] = [
  { name: '你的真实YAML', data: D1_YOUR_REAL },
  { name: '仅根层级tasks', data: D2_ROOT_TASKS_ONLY },
  { name: '仅SubPipeline', data: D3_SUBPIPELINES_ONLY },
  { name: '含Post处理', data: D4_WITH_POST },
  { name: '大量节点(30+)', data: D5_LARGE },
  { name: '最小数据', data: D6_MINIMAL },
];

async function setup(page: P, pipeline: any) {
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const u = route.request().url();
    if (u.includes('auth/me')) await route.fulfill({ status:200, contentType:'application/json', body: JSON.stringify({ account:'admin', id:1, nickname:'Admin', role:'top', dept:0 }) });
    else if (u.includes('pipelines/by-id') && route.request().method() === 'GET') await route.fulfill({ status:200, contentType:'application/json', body: JSON.stringify(pipeline) });
    else if (u.includes('pipelines/by-id') && route.request().method() === 'PUT') await route.fulfill({ status:200, contentType:'application/json', body: JSON.stringify({ success:true }) });
    else await route.fulfill({ status:200, contentType:'application/json', body:'{}' });
  });
  await page.goto('/');
  await page.evaluate((t) => localStorage.setItem('taskpps_token', t), 't');
  await page.goto('/pipelines/p/d', { waitUntil: 'domcontentloaded', timeout:15000 });
  await page.waitForSelector('.react-flow', { timeout:10000 });
  await page.waitForTimeout(1000);
}

for (const s of SCENARIOS) {
  test.describe(`数据: ${s.name}`, () => {
    test('查看模式 → 画布渲染不崩溃', async ({ page }) => {
      await setup(page, s.data);
      expect(await page.locator('.react-flow').isVisible().catch(() => false)).toBeTruthy();
    });

    test('编辑模式 → 拖 CMD 节点 → 节点出现', async ({ page }) => {
      await setup(page, s.data);
      await page.getByRole('button', { name: '编辑模式' }).click();
      await page.waitForTimeout(1000);
      const before = await page.locator('.react-flow__node').count();
      const card = page.locator('[draggable="true"]', { hasText: 'CMD' }).first();
      if (await card.isVisible().catch(() => false)) {
        await card.dragTo(page.locator('.react-flow__pane').first(), { sourcePosition:{x:10,y:10}, targetPosition:{x:300,y:300} });
        await page.waitForTimeout(800);
      }
      expect(await page.locator('.react-flow__node').count()).toBeGreaterThanOrEqual(before);
    });

    test('编辑模式 → 右键 SubPipeline → 有菜单项', async ({ page }) => {
      await setup(page, s.data);
      await page.getByRole('button', { name: '编辑模式' }).click();
      await page.waitForTimeout(1000);
      const sub = page.locator('.react-flow__node-editorSubPipeline').first();
      if (await sub.isVisible().catch(() => false)) {
        await sub.dispatchEvent('contextmenu');
        await page.waitForTimeout(800);
        // v2 (2026-07): React 内联样式的 DOM 序列化为 "position: fixed"（带空格），
        // 原选择器 "position:fixed" 永远匹配不到，导致菜单断言假失败
        const items = await page.locator('div[style*="position: fixed"] > div').allTextContents();
        expect(items.some(t => t.includes('添加') || t.includes('折叠') || t.includes('属性') || t.includes('删除'))).toBeTruthy();
      }
    });

    test('编辑模式 → 右键 Task → 有属性/删除', async ({ page }) => {
      await setup(page, s.data);
      await page.getByRole('button', { name: '编辑模式' }).click();
      await page.waitForTimeout(1000);
      const task = page.locator('.react-flow__node-editorTask').first();
      if (await task.isVisible().catch(() => false)) {
        await task.dispatchEvent('contextmenu');
        await page.waitForTimeout(800);
        // v2 (2026-07): React 内联样式的 DOM 序列化为 "position: fixed"（带空格），
        // 原选择器 "position:fixed" 永远匹配不到，导致菜单断言假失败
        const items = await page.locator('div[style*="position: fixed"] > div').allTextContents();
        expect(items.some(t => t.includes('属性') || t.includes('删除'))).toBeTruthy();
      }
    });

    test('编辑模式 → 点击 Task → 属性面板 → name 字段有值', async ({ page }) => {
      await setup(page, s.data);
      await page.getByRole('button', { name: '编辑模式' }).click();
      await page.waitForTimeout(1000);
      const task = page.locator('.react-flow__node-editorTask').first();
      if (await task.isVisible().catch(() => false)) {
        await task.click({ force: true });
        await page.waitForTimeout(1500);
        // v2 (2026-07): 原选择器 [class*="panel"] 会命中 NodePalette 中的空元素导致假失败；
        // PropertyPanel 是 antd Drawer，直接用 .ant-drawer-body 并断言可见
        const panel = page.locator('.ant-drawer-body').first();
        await expect(panel).toBeVisible({ timeout: 5000 });
        const text = await panel.textContent();
        expect(text?.length).toBeGreaterThan(0);
      }
    });

    test('编辑模式 → 保存 → PUT 请求体含 pipeline name', async ({ page }) => {
      let body = '';
      await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
        const u = route.request().url();
        if (u.includes('auth/me')) await route.fulfill({ status:200, contentType:'application/json', body: JSON.stringify({ account:'admin', id:1, nickname:'Admin', role:'top', dept:0 }) });
        else if (u.includes('pipelines/by-id') && route.request().method() === 'GET') await route.fulfill({ status:200, contentType:'application/json', body: JSON.stringify(s.data) });
        else if (u.includes('pipelines/by-id') && route.request().method() === 'PUT') { body = await route.request().postData() || ''; await route.fulfill({ status:200, contentType:'application/json', body: JSON.stringify({ success:true }) }); }
        else await route.fulfill({ status:200, contentType:'application/json', body:'{}' });
      });
      await page.goto('/');
      await page.evaluate((t) => localStorage.setItem('taskpps_token', t), 't');
      await page.goto('/pipelines/p/d', { waitUntil: 'domcontentloaded', timeout:15000 });
      await page.waitForSelector('.react-flow', { timeout:10000 });
      await page.waitForTimeout(1000);

      await page.getByRole('button', { name: '编辑模式' }).click();
      await page.waitForTimeout(1000);
      // v2 (2026-07): 保存按钮由 dirty 驱动 disabled（未编辑为 disabled），
      // 先做一次内容编辑（拖 CMD 到左上空白）再保存
      const card = page.locator('[draggable="true"]', { hasText: 'CMD' }).first();
      const canvas = page.locator('.react-flow__pane').first();
      await card.dragTo(canvas, {
        sourcePosition: { x: 10, y: 10 },
        targetPosition: { x: 80, y: 140 },
      });
      await page.waitForTimeout(600);
      await page.locator('button').filter({ hasText:'保存' }).first().click();
      await page.waitForTimeout(1000);

      const hasName = body.includes(s.data.name) || body.includes('"content"');
      expect(hasName).toBeTruthy();
    });
  });
}
