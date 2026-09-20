import { describe, it, expect } from 'vitest';
import { yamlToNodes } from '../yamlToNodes';
import { layoutGraph } from '../layoutGraph';
import { COMPLEX_SCENARIOS } from './fixtures/complexPipelines';
import {
  assertNoSiblingOverlap,
  assertChildrenInsideContainers,
  assertFinitePositions,
  assertEdgesResolvable,
  nodeSizeOf,
  nodeRectOf,
  rectsOverlap,
} from './fixtures/layoutAssertions';

/**
 * 复杂场景结构不变量测试
 *
 * 每个场景独立验证以下不变量（不变量对所有合法输入都必须成立）：
 *   1. 反序列化 + 布局不抛异常，坐标全部有限
 *   2. 同父节点两两不重叠
 *   3. 子节点不越出父容器
 *   4. 边端点可解析（无悬空边）
 *   5. 布局确定性（同输入两次结果一致）
 *   6. 节点 ID 唯一
 *
 * 已知非法输入（孤儿依赖/环形依赖/重名任务）的容错行为单独分组测试，
 * 用于暴露产品当前的真实表现，而不是假设它一定正确。
 */

describe.each(COMPLEX_SCENARIOS)('复杂场景 [$id] $title', ({ id, pipeline }) => {
  it('反序列化 + 布局不抛异常，坐标有限', () => {
    const { nodes, edges } = yamlToNodes(pipeline);
    const laid = layoutGraph(nodes, edges);
    assertFinitePositions(laid, id);
  });

  it('同父节点两两不重叠', () => {
    const { nodes, edges } = yamlToNodes(pipeline);
    const laid = layoutGraph(nodes, edges);
    assertNoSiblingOverlap(laid, id);
  });

  it('子节点不越出父容器', () => {
    const { nodes, edges } = yamlToNodes(pipeline);
    const laid = layoutGraph(nodes, edges);
    assertChildrenInsideContainers(laid, id);
  });

  it('边端点可解析（无悬空边）', () => {
    const { nodes, edges } = yamlToNodes(pipeline);
    assertEdgesResolvable(nodes, edges, id);
  });

  it('布局确定性：两次布局结果一致', () => {
    const g1 = yamlToNodes(pipeline);
    const g2 = yamlToNodes(pipeline);
    const l1 = layoutGraph(g1.nodes, g1.edges);
    const l2 = layoutGraph(g2.nodes, g2.edges);
    const snap = (ns: ReturnType<typeof layoutGraph>) =>
      ns.map((n) => ({ id: n.id, x: n.position.x, y: n.position.y, style: n.style ?? null }));
    expect(snap(l1)).toEqual(snap(l2));
  });

  it('节点 ID 唯一', () => {
    const { nodes } = yamlToNodes(pipeline);
    const ids = nodes.map((n) => n.id);
    const dup = ids.filter((id, i) => ids.indexOf(id) !== i);
    expect(dup, `重复节点 ID: ${[...new Set(dup)].join(', ')}`).toEqual([]);
  });

  it('边 ID 唯一且无自环边', () => {
    const { edges } = yamlToNodes(pipeline);
    const ids = edges.map((e) => e.id);
    expect(new Set(ids).size, `存在重复边 ID: ${ids.filter((id, i) => ids.indexOf(id) !== i).join(', ')}`).toBe(ids.length);
    const selfLoops = edges.filter((e) => e.source === e.target).map((e) => e.id);
    expect(selfLoops, `存在自环边: ${selfLoops.join(', ')}`).toEqual([]);
  });
});

// ─────────────────────────────────────────────────────────────
// 性能压力：60 任务、3 层容器
// ─────────────────────────────────────────────────────────────
describe('复杂场景 — 性能压力', () => {
  it('60 任务大图布局耗时 < 2000ms', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'many-tasks')!;
    const { nodes, edges } = yamlToNodes(scenario.pipeline);
    const start = performance.now();
    layoutGraph(nodes, edges);
    const elapsed = performance.now() - start;
    expect(elapsed, `布局耗时 ${elapsed.toFixed(0)}ms 超出预算`).toBeLessThan(2000);
  });

  it('60 任务大图总高度有限且容器依次向下排列', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'many-tasks')!;
    const { nodes, edges } = yamlToNodes(scenario.pipeline);
    const laid = layoutGraph(nodes, edges);
    const subY = (name: string) => laid.find((n) => n.id === `__pipeline__${name}`)!.position.y;
    expect(subY('stage-a')).toBeLessThan(subY('stage-b'));
    expect(subY('stage-b')).toBeLessThan(subY('stage-c'));
    for (const n of laid) {
      expect(Number.isFinite(n.position.y)).toBe(true);
    }
  });
});

// ─────────────────────────────────────────────────────────────
// 依赖语义正确性（与执行引擎 server/taskpps/domain/dag.py 对齐）
// ─────────────────────────────────────────────────────────────
describe('复杂场景 — 依赖语义正确性', () => {
  it('菱形依赖：不生成错误的隐式顺序边，b/c 同 rank', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'diamond')!;
    const { nodes, edges } = yamlToNodes(scenario.pipeline);
    const implicit = edges.filter((e) => e.data?.edgeType === 'implicit');
    expect(
      implicit.map((e) => `${e.source}→${e.target}`),
      '有显式 depends_on 的任务不应再补隐式顺序边（否则菱形被渲染成串行链）',
    ).toEqual([]);
    const laid = layoutGraph(nodes, edges);
    const y = (id: string) => laid.find((n) => n.id === id)!.position.y;
    expect(y('__task__build.b')).toBe(y('__task__build.c'));
  });

  it('无 depends_on 的任务按引擎语义补隐式边（依赖前一个任务）', () => {
    const pipeline = {
      name: 'implicit-check',
      pipelines: [
        {
          name: 's',
          depends_on: [],
          tasks: [
            { name: 'a', env: {}, retry: 0, depends_on: [] },
            { name: 'b', env: {}, retry: 0, depends_on: ['a'] },
            { name: 'c', env: {}, retry: 0, depends_on: [] },
          ],
        },
      ],
    };
    const { edges } = yamlToNodes(pipeline);
    const implicit = edges
      .filter((e) => e.data?.edgeType === 'implicit')
      .map((e) => `${e.source}→${e.target}`);
    // b 有显式依赖不补；c 无依赖 → 补 b→c；a 是首个任务无前驱
    expect(implicit).toEqual(['__task__s.b→__task__s.c']);
  });
});

// ─────────────────────────────────────────────────────────────
// 非法/边界输入的容错行为（暴露当前真实表现）
// ─────────────────────────────────────────────────────────────
describe('复杂场景 — 非法输入容错', () => {
  it('孤儿依赖：不生成指向不存在任务的悬空边', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'orphan-deps')!;
    const { nodes, edges } = yamlToNodes(scenario.pipeline);
    const ids = new Set(nodes.map((n) => n.id));
    const dangling = edges.filter((e) => !ids.has(e.source) || !ids.has(e.target));

    expect(
      dangling.map((e) => `${e.source}→${e.target}`),
      'yamlToNodes 不应生成悬空边',
    ).toEqual([]);
  });

  it('环形依赖：布局不崩溃，边保留环', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'cyclic')!;
    const { nodes, edges } = yamlToNodes(scenario.pipeline);
    const laid = layoutGraph(nodes, edges);
    assertFinitePositions(laid, 'cyclic');
    expect(edges.some((e) => e.data?.edgeType === 'explicit')).toBe(true);
  });

  it('同容器重名任务：只渲染第一个实例，无重复节点 ID', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'duplicate-names')!;
    const { nodes } = yamlToNodes(scenario.pipeline);
    const ids = nodes.map((n) => n.id);
    const dup = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
    expect(dup, `存在重复节点 ID: ${dup.join(', ')}`).toEqual([]);
    // 3 个重名任务只保留 1 个
    expect(nodes.filter((n) => n.type === 'editorTask')).toHaveLength(1);
  });

  it('重复依赖/自依赖：边 ID 唯一、无自环、无重复连接', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'edge-cases')!;
    const { edges } = yamlToNodes(scenario.pipeline);

    // 1) 边 ID 全局唯一（重复 depends_on 会产生相同 ID，击穿 React key）
    const ids = edges.map((e) => e.id);
    const dupIds = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
    expect(dupIds, `重复边 ID: ${dupIds.join(', ')}`).toEqual([]);

    // 2) 无自环边（任务自依赖 / 容器自依赖）
    const selfLoops = edges.filter((e) => e.source === e.target).map((e) => e.id);
    expect(selfLoops, `自环边: ${selfLoops.join(', ')}`).toEqual([]);

    // 3) 同一对端点 + 同一 handle 只允许一条边（重复依赖应被去重）
    const keys = edges.map(
      (e) => `${e.source}→${e.target}#${e.sourceHandle ?? ''}#${e.targetHandle ?? ''}`,
    );
    const dupKeys = [...new Set(keys.filter((k, i) => keys.indexOf(k) !== i))];
    expect(dupKeys, `重复连接: ${dupKeys.join(', ')}`).toEqual([]);
  });

  it('顶层 tasks：规范化为同名 SubPipeline 后渲染', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'top-level-tasks')!;
    const { nodes } = yamlToNodes(scenario.pipeline);
    // v3 (2026-07): yamlToNodes 入口与后端 _normalize 对齐，顶层 tasks 包装为
    // 以流水线名命名的 SubPipeline，任务不再不可见
    const taskNodes = nodes.filter((n) => n.type === 'editorTask');
    expect(taskNodes.map((n) => n.id).sort()).toEqual([
      '__task__scenario-top-level-tasks.cleanup',
      '__task__scenario-top-level-tasks.init',
    ]);
    expect(nodes.some((n) => n.id === '__pipeline__scenario-top-level-tasks')).toBe(true);
  });

  it('空子流水线：依赖它的容器仍保持顺序', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'empty-sub')!;
    const { nodes, edges } = yamlToNodes(scenario.pipeline);
    const laid = layoutGraph(nodes, edges);
    assertNoSiblingOverlap(laid, 'empty-sub');
    // empty-one 无 tasks，yamlToNodes 不生成跨容器边；这会导致依赖方向丢失。
    // 记录期望：normal 应排在 empty-one 下方。
    const empty = laid.find((n) => n.id === '__pipeline__empty-one')!;
    const normal = laid.find((n) => n.id === '__pipeline__normal')!;
    expect(normal.position.y, '空容器依赖关系应在布局中保持').toBeGreaterThan(empty.position.y);
  });
});

// ─────────────────────────────────────────────────────────────
// 大容器与全局重叠（跨层级绝对坐标）
// ─────────────────────────────────────────────────────────────
describe('复杂场景 — 容器间不重叠', () => {
  it.each(COMPLEX_SCENARIOS.filter((s) => !['duplicate-names', 'empty'].includes(s.id)))(
    '[$id] 根层容器互不重叠',
    ({ id, pipeline }) => {
      const { nodes, edges } = yamlToNodes(pipeline);
      const laid = layoutGraph(nodes, edges);
      const roots = laid.filter((n) => !n.parentId);
      for (let i = 0; i < roots.length; i++) {
        for (let j = i + 1; j < roots.length; j++) {
          const a = nodeRectOf(roots[i]);
          const b = nodeRectOf(roots[j]);
          expect(
            rectsOverlap(a, b),
            `${id}: 根节点 ${roots[i].id} 与 ${roots[j].id} 重叠`,
          ).toBe(false);
        }
      }
    },
  );

  it('长文本节点宽度不会无限膨胀（名称被组件截断）', () => {
    const scenario = COMPLEX_SCENARIOS.find((s) => s.id === 'long-names')!;
    const { nodes } = yamlToNodes(scenario.pipeline);
    for (const n of nodes.filter((x) => x.type === 'editorTask')) {
      const { width } = nodeSizeOf(n);
      expect(width).toBeLessThanOrEqual(400);
    }
  });
});
