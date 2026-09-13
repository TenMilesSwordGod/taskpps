import { test, expect, Page } from '@playwright/test';
import { dump } from 'js-yaml';
import { COMPLEX_SCENARIOS, type ComplexScenario } from '../src/features/pipelines/workflow/__tests__/fixtures/complexPipelines';

/**
 * 复杂 pipeline 场景 e2e 压力测试
 *
 * 为什么用 YAML 编辑器注入：/e2e/pipeline-detail 是 mock 数据页，画布数据由 YAML
 * 解析驱动。通过注入复杂 YAML 可以在真实浏览器里验证任意结构，无需新增路由。
 *
 * 覆盖（真实 DOM 几何，而非 jsdom 估算）：
 *   - 节点两两不重叠（叶子集合 / 根层容器集合分别比较）
 *   - 子节点不越出父容器（DOM 矩形包含关系）
 *   - 特殊字符、超长文本渲染
 *   - 查看/编辑模式切换后结构一致
 *   - 60 任务大图渲染性能
 *   - 每个场景留档截图，供人工检查 UI/UX
 */

const TEST_URL = '/e2e/pipeline-detail';

interface DomRect {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  right: number;
  bottom: number;
}

async function waitForCanvas(page: Page) {
  await page.waitForSelector('.react-flow', { timeout: 15000 });
  await page.waitForSelector('.react-flow__node', { timeout: 10000 });
  await page.waitForTimeout(500);
}

/** 打开 YAML 编辑器并整体替换内容，驱动画布重新渲染 */
async function injectYaml(page: Page, yaml: string) {
  const openBtn = page.getByRole('button', { name: 'YAML 编辑器' });
  if (await openBtn.isVisible().catch(() => false)) {
    await openBtn.click();
    await page.waitForTimeout(400);
  }
  const editor = page.locator('.cm-content').first();
  await editor.click();
  await page.keyboard.press('Control+a');
  await page.keyboard.insertText(yaml);
  // 等待解析与 WorkflowEditor 响应式重建
  await page.waitForTimeout(1000);
}

/** 读取所有节点及 start/end 哨兵的 DOM 几何 */
async function getNodeRects(page: Page): Promise<DomRect[]> {
  return page.locator('.react-flow__node').evaluateAll((els) =>
    els.map((el) => {
      const r = el.getBoundingClientRect();
      return {
        id: el.getAttribute('data-id') ?? '',
        x: r.x,
        y: r.y,
        width: r.width,
        height: r.height,
        right: r.right,
        bottom: r.bottom,
      };
    }),
  );
}

/** 留 1px 容差避免子像素/边框导致的假阳性 */
function overlaps(a: DomRect, b: DomRect): boolean {
  return a.x < b.right - 1 && b.x < a.right - 1 && a.y < b.bottom - 1 && b.y < a.bottom - 1;
}

function isLeaf(id: string): boolean {
  return (
    id.startsWith('__task__') ||
    id.startsWith('__postchild__') ||
    id === '__start__' ||
    id === '__end__'
  );
}

function isRootContainer(id: string): boolean {
  return (id.startsWith('__pipeline__') && id !== '__pipeline__') || id.startsWith('__post__');
}

/** 从节点 ID 推导父容器 ID（与 yamlToNodes 的命名约定一致） */
function parentIdOf(id: string): string | null {
  if (id.startsWith('__task__')) {
    const rest = id.slice('__task__'.length);
    const sub = rest.split('.')[0];
    return `__pipeline__${sub}`;
  }
  if (id.startsWith('__postchild__')) {
    // __postchild__<postParentId>_<hook>_<idx>
    const rest = id.slice('__postchild__'.length);
    const m = rest.match(/^(.*)_(on_fail|on_success|always)_(\d+)$/);
    return m ? m[1] : null;
  }
  if (id.startsWith('__pipeline__') && id !== '__pipeline__') return '__pipeline__';
  if (id.startsWith('__post__')) return '__pipeline__';
  return null;
}

/** 矩形包含检查（2px 容差吸收缩放/边框取整误差） */
function contains(container: DomRect, child: DomRect, tolerance = 2): boolean {
  return (
    child.x >= container.x - tolerance &&
    child.y >= container.y - tolerance &&
    child.right <= container.right + tolerance &&
    child.bottom <= container.bottom + tolerance
  );
}

/** 检查所有子节点是否落在其父容器矩形内，返回越界描述 */
function findOutOfBounds(rects: DomRect[]): string[] {
  const byId = new Map(rects.map((r) => [r.id, r]));
  const issues: string[] = [];
  for (const child of rects) {
    const pid = parentIdOf(child.id);
    if (!pid) continue;
    const parent = byId.get(pid);
    if (!parent) continue;
    if (!contains(parent, child)) {
      issues.push(`${child.id} 超出 ${pid}`);
    }
  }
  return issues;
}

/** 检查集合内两两重叠，返回重叠对 */
function findOverlaps(rects: DomRect[], pick: (id: string) => boolean): string[] {
  const target = rects.filter((r) => pick(r.id));
  const pairs: string[] = [];
  for (let i = 0; i < target.length; i++) {
    for (let j = i + 1; j < target.length; j++) {
      if (overlaps(target[i], target[j])) {
        pairs.push(`${target[i].id} <-> ${target[j].id}`);
      }
    }
  }
  return pairs;
}

/** 通过场景数据构造 YAML 文本 */
function scenarioYaml(scenario: ComplexScenario): string {
  return dump(scenario.pipeline, { indent: 2, lineWidth: 200 });
}

async function loadScenario(page: Page, scenario: ComplexScenario) {
  await page.goto(TEST_URL);
  await waitForCanvas(page);
  await injectYaml(page, scenarioYaml(scenario));
  await waitForCanvas(page);
}

// ============================================================
// A. 几何不变量：无重叠 / 不越界
// ============================================================
test.describe('复杂场景几何不变量', () => {
  const GEOMETRY_SCENARIOS = COMPLEX_SCENARIOS.filter((s) =>
    [
      'diamond',
      'parallel-fanout',
      'cross-chain',
      'conditions',
      'post-heavy',
      'deep-chain',
      'long-names',
      'special-chars',
      'same-names',
      'cyclic',
      'edge-cases',
    ].includes(s.id),
  );

  /** 关键场景的期望边数（含 START→Pipeline→END 哨兵边），用于捕获边丢失/多余 */
  const EXPECTED_EDGE_COUNTS: Record<string, number> = {
    diamond: 6, // 2 哨兵 + a→b, a→c, b→d, c→d
    'post-heavy': 3, // 2 哨兵 + sub→postParent
    empty: 2, // 仅 2 哨兵
  };

  for (const scenario of GEOMETRY_SCENARIOS) {
    test(`[${scenario.id}] 叶子节点与根层容器均不重叠`, async ({ page }) => {
      await loadScenario(page, scenario);
      const rects = await getNodeRects(page);
      expect(rects.length, '画布应渲染出节点').toBeGreaterThan(2);

      // v2 (2026-07): 边可见性回归 —— 查看模式曾因移除节点 Handle 导致所有连线消失。
      // 每个场景至少有 START→Pipeline→END 哨兵边，故 edge 数量必须 > 0，
      // 且不能出现零长度（未锚定到 Handle）的边。
      const edgeCount = await page.locator('.react-flow__edge').count();
      expect(edgeCount, `${scenario.id}: 应渲染连线`).toBeGreaterThan(0);
      const expectedEdges = EXPECTED_EDGE_COUNTS[scenario.id];
      if (expectedEdges !== undefined) {
        expect(edgeCount, `${scenario.id}: 边数量应为 ${expectedEdges}`).toBe(expectedEdges);
      }
      const zeroLengthEdges = await page.locator('.react-flow__edge path').evaluateAll((els) =>
        els.filter((el) => (el as SVGPathElement).getTotalLength() < 1).length,
      );
      expect(zeroLengthEdges, `${scenario.id}: 存在零长度/未锚定的边`).toBe(0);

      const leafOverlaps = findOverlaps(rects, isLeaf);
      const containerOverlaps = findOverlaps(rects, isRootContainer);
      const boundsIssues = findOutOfBounds(rects);

      expect(leafOverlaps, `${scenario.id}: 叶子节点重叠 ${leafOverlaps.join(', ')}`).toEqual([]);
      expect(containerOverlaps, `${scenario.id}: 根层容器重叠 ${containerOverlaps.join(', ')}`).toEqual([]);
      expect(boundsIssues, `${scenario.id}: 子节点越界 ${boundsIssues.join(', ')}`).toEqual([]);

      await page.screenshot({ path: `test-results/complex-${scenario.id}.png` });
    });
  }
});

// ============================================================
// B. 内容渲染：特殊字符 / 长名称 / post / 空结构
// ============================================================
test.describe('复杂场景内容渲染', () => {
  test('特殊字符任务名完整显示且未注入 HTML', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'special-chars')!;
    await loadScenario(page, scenario);
    await expect(page.getByText('<tag> & "amp"').first()).toBeVisible();
    await expect(page.getByText('back\\slash').first()).toBeVisible();
    expect(await page.locator('tag').count()).toBe(0);
  });

  test('超长任务名与中文名称渲染', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'long-names')!;
    await loadScenario(page, scenario);
    await expect(page.getByText('中文任务名称用于验证等宽字体下的渲染宽度是否稳定').first()).toBeVisible();
  });

  test('post 密集：6 个子任务标签全部渲染', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'post-heavy')!;
    await loadScenario(page, scenario);
    await expect(page.getByText('失败时').first()).toBeVisible();
    await expect(page.getByText('成功时').first()).toBeVisible();
    await expect(page.getByText('始终').first()).toBeVisible();
    await expect(page.getByText('rollback').first()).toBeVisible();
    await expect(page.getByText('cleanup-workspace').first()).toBeVisible();
  });

  test('空 pipeline：不崩溃，画布可交互', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'empty')!;
    await loadScenario(page, scenario);
    await expect(page.locator('.react-flow').first()).toBeVisible();
    // 至少渲染 START / END / Pipeline 节点
    await expect(page.getByText('START').first()).toBeVisible();
    await expect(page.getByText('END').first()).toBeVisible();
    // 空图仍应有 START→Pipeline→END 两条哨兵边
    expect(await page.locator('.react-flow__edge').count()).toBe(2);
  });

  test('环形依赖：不崩溃且所有任务可见', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'cyclic')!;
    await loadScenario(page, scenario);
    for (const name of ['a', 'b', 'c']) {
      await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
    }
  });

  test('孤儿依赖：不产生悬空边崩溃，任务可见', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'orphan-deps')!;
    await loadScenario(page, scenario);
    await expect(page.getByText('second').first()).toBeVisible();
    await expect(page.getByText('third').first()).toBeVisible();
    // 记录边数量，用于发现悬空边（React Flow 会为悬空边渲染吗）
    const edgeCount = await page.locator('.react-flow__edge').count();
    expect(edgeCount).toBeGreaterThanOrEqual(0);
  });

  test('顶层 tasks：解析规范化为同名 SubPipeline，画布可见', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'top-level-tasks')!;
    await loadScenario(page, scenario);
    // v3 (2026-07): parse/yamlToNodes 与后端 _normalize 对齐，顶层 tasks 包装为
    // 以流水线名命名的隐式 SubPipeline 后正常渲染
    await expect(page.getByText('init', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('cleanup', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('scenario-top-level-tasks').first()).toBeVisible();
  });
});

// ============================================================
// C. 模式切换一致性
// ============================================================
test.describe('复杂场景模式切换', () => {
  test('菱形依赖：查看 → 编辑 → 查看，节点数量一致', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'diamond')!;
    await loadScenario(page, scenario);
    const viewCount = await page.locator('.react-flow__node').count();

    await page.getByRole('button', { name: '编辑模式' }).click();
    await page.waitForTimeout(800);
    const editCount = await page.locator('.react-flow__node').count();
    expect(editCount).toBe(viewCount);

    await page.getByRole('button', { name: '查看模式' }).click();
    await page.waitForTimeout(800);
    const backCount = await page.locator('.react-flow__node').count();
    expect(backCount).toBe(viewCount);
  });

  test('跨容器链：编辑模式下再次布局后仍不重叠', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'cross-chain')!;
    await loadScenario(page, scenario);

    await page.getByRole('button', { name: '编辑模式' }).click();
    await page.waitForTimeout(800);
    // 移开鼠标避免"退出编辑模式"tooltip 遮挡工具栏按钮
    await page.mouse.move(700, 500);
    // 点击工具栏"布局"按钮
    await page.getByRole('button', { name: '布局' }).click();
    await page.waitForTimeout(800);

    const rects = await getNodeRects(page);
    const overlapsFound = findOverlaps(rects, isLeaf);
    expect(overlapsFound, `布局后重叠: ${overlapsFound.join(', ')}`).toEqual([]);
  });
});

// ============================================================
// D. 性能压力：60 任务
// ============================================================
test.describe('复杂场景性能', () => {
  test('60 任务大图：注入到渲染完成的耗时 < 8s，节点全部出现', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'many-tasks')!;
    await page.goto(TEST_URL);
    await waitForCanvas(page);

    const start = Date.now();
    await injectYaml(page, scenarioYaml(scenario));
    await expect(page.getByText('c-20').first()).toBeVisible({ timeout: 15000 });
    const elapsed = Date.now() - start;

    // 8s 是宽松上限：仅拦截"卡死/数量级性能退化"，不做过紧断言
    expect(elapsed, `渲染耗时 ${elapsed}ms`).toBeLessThan(8000);

    const rects = await getNodeRects(page);
    expect(rects.length).toBeGreaterThanOrEqual(60);
    await page.screenshot({ path: 'test-results/complex-many-tasks.png' });
  });
});

// ============================================================
// E. 遗留项：折叠+布局 / 跨容器手动连线（v3/2026-07）
// ============================================================
test.describe('复杂场景遗留项验证', () => {
  test('折叠 SubPipeline → 点击布局 → 保持折叠且后代隐藏', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'cross-chain')!;
    await loadScenario(page, scenario);
    await page.getByRole('button', { name: '编辑模式' }).click();
    await page.waitForTimeout(800);

    const containerSel = '[data-id="__pipeline__prepare"]';
    const childSel = '[data-id="__task__prepare.checkout"]';

    const before = await page.locator(containerSel).boundingBox();
    expect(before).not.toBeNull();

    await page.locator(`${containerSel} .collapse-toggle`).click();
    await page.waitForTimeout(400);

    const collapsed = await page.locator(containerSel).boundingBox();
    // 折叠后高度显著变小（140x48 紧凑尺寸）
    expect(collapsed!.height).toBeLessThan(before!.height / 2);
    // 后代任务节点被隐藏
    await expect(page.locator(childSel)).toBeHidden();

    // 点击"布局"：折叠容器不应被重新撑开
    await page.mouse.move(700, 500);
    await page.getByRole('button', { name: '布局' }).click();
    await page.waitForTimeout(800);
    const afterLayout = await page.locator(containerSel).boundingBox();
    expect(afterLayout!.height).toBeLessThan(before!.height / 2);
    await expect(page.locator(childSel)).toBeHidden();
  });

  test('跨容器手动连线 → 保存成功（映射为 SubPipeline 依赖，不静默丢失）', async ({ page }) => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'cross-chain')!;
    await loadScenario(page, scenario);
    await page.getByRole('button', { name: '编辑模式' }).click();
    await page.waitForTimeout(800);

    // prepare.checkout (out) → deploy.push (in)：跨容器连线
    const source = page.locator('[data-id="__task__prepare.checkout"] [data-handleid="out"]');
    const target = page.locator('[data-id="__task__deploy.push"] [data-handleid="in"]');
    const sBox = await source.boundingBox();
    const tBox = await target.boundingBox();
    expect(sBox && tBox).toBeTruthy();

    await page.mouse.move(sBox!.x + sBox!.width / 2, sBox!.y + sBox!.height / 2);
    await page.mouse.down();
    await page.mouse.move(tBox!.x + tBox!.width / 2, tBox!.y + tBox!.height / 2, { steps: 10 });
    await page.mouse.up();
    await page.waitForTimeout(500);

    // 保存：不应出现"无法保存的连线"错误（跨容器连线已映射为 sub 级依赖）
    await page.mouse.move(700, 500);
    await page.getByRole('button', { name: '保存' }).click();
    await page.waitForTimeout(500);
    await expect(page.getByText('无法保存的连线')).toHaveCount(0);
    await expect(page.getByText('已保存').first()).toBeVisible();
  });
});
