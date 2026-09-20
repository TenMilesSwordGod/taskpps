import { describe, it, expect } from 'vitest';
import type { Node, Edge } from '@xyflow/react';
import { layoutGraph } from '../layoutGraph';

/**
 * 容器感知分层布局的验收测试（Phase 1）
 *
 * 目标（对应现有渲染的三个症状）:
 *   1. 节点重叠/越界 —— 同层节点矩形不相交，子节点必须落在父容器内
 *   2. 布局错位 —— 层级方向正确（TB），容器尺寸由内容撑开
 *   3. 布局跳动 —— 同输入两次布局结果必须完全一致
 */

/** 测试辅助：构造节点（默认无测量尺寸，走类型默认值） */
function makeNode(
  id: string,
  type: string,
  extra: Partial<Node> = {},
): Node {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    data: {},
    ...extra,
  };
}

function makeEdge(id: string, source: string, target: string): Edge {
  return { id, source, target };
}

/** 读取节点宽高（测试内联，避免依赖实现内部函数） */
function nodeRect(n: Node): { x: number; y: number; w: number; h: number } {
  const style = n.style as { width?: number; height?: number } | undefined;
  const measured = (n as { measured?: { width?: number; height?: number } }).measured;
  const w = measured?.width ?? (typeof style?.width === 'number' ? style.width : undefined) ?? 180;
  const h = measured?.height ?? (typeof style?.height === 'number' ? style.height : undefined) ?? 56;
  return { x: n.position.x, y: n.position.y, w, h };
}

/** 查找节点并断言存在 */
function find(nodes: Node[], id: string): Node {
  const n = nodes.find((x) => x.id === id);
  expect(n, `节点 ${id} 应存在`).toBeDefined();
  return n!;
}

describe('layoutGraph — 基础行为', () => {
  it('空图返回空数组', () => {
    expect(layoutGraph([], [])).toEqual([]);
  });

  it('单节点：坐标有限且不改 id/data', () => {
    const nodes = [makeNode('a', 'editorTask', { data: { label: 'a' } })];
    const out = layoutGraph(nodes, []);
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('a');
    expect(out[0].data).toEqual({ label: 'a' });
    expect(Number.isFinite(out[0].position.x)).toBe(true);
    expect(Number.isFinite(out[0].position.y)).toBe(true);
  });

  it('不修改输入节点（position/style 原样保留）', () => {
    const nodes = [makeNode('a', 'editorTask', { position: { x: 7, y: 9 } })];
    layoutGraph(nodes, []);
    expect(nodes[0].position).toEqual({ x: 7, y: 9 });
  });

  it('链式 a→b：b 在 a 下方（rankdir=TB）', () => {
    const nodes = [makeNode('a', 'editorTask'), makeNode('b', 'editorTask')];
    const out = layoutGraph(nodes, [makeEdge('e1', 'a', 'b')]);
    const a = nodeRect(find(out, 'a'));
    const b = nodeRect(find(out, 'b'));
    expect(b.y).toBeGreaterThan(a.y);
  });

  it('分支 a→b, a→c：b/c 同 rank（y 相同）且水平不相交', () => {
    const nodes = [
      makeNode('a', 'editorTask'),
      makeNode('b', 'editorTask'),
      makeNode('c', 'editorTask'),
    ];
    const out = layoutGraph(nodes, [makeEdge('e1', 'a', 'b'), makeEdge('e2', 'a', 'c')]);
    const b = nodeRect(find(out, 'b'));
    const c = nodeRect(find(out, 'c'));
    expect(b.y).toBe(c.y);
    const overlap = b.x < c.x + c.w && c.x < b.x + b.w;
    expect(overlap).toBe(false);
  });

  it('START → Pipeline → END：END 在最底部', () => {
    const nodes = [
      makeNode('__start__', 'editorStartEnd', { data: { variant: 'start' } }),
      makeNode('__pipeline__', 'editorPipeline', { style: { width: 400, height: 200 } }),
      makeNode('__end__', 'editorStartEnd', { data: { variant: 'end' } }),
    ];
    const edges = [
      makeEdge('e1', '__start__', '__pipeline__'),
      makeEdge('e2', '__pipeline__', '__end__'),
    ];
    const out = layoutGraph(nodes, edges);
    const start = nodeRect(find(out, '__start__'));
    const pipeline = nodeRect(find(out, '__pipeline__'));
    const end = nodeRect(find(out, '__end__'));
    expect(pipeline.y).toBeGreaterThan(start.y);
    expect(end.y).toBeGreaterThan(pipeline.y);
  });
});

describe('layoutGraph — 容器包裹与嵌套', () => {
  it('SubPipeline 容器包裹所有直接子节点，子节点坐标相对容器', () => {
    const nodes = [
      makeNode('sub', 'editorSubPipeline', { style: { width: 260, height: 140 } }),
      makeNode('a', 'editorTask', { parentId: 'sub' }),
      makeNode('b', 'editorTask', { parentId: 'sub' }),
      makeNode('c', 'editorTask', { parentId: 'sub' }),
    ];
    const edges = [
      makeEdge('e1', 'a', 'b'),
      makeEdge('e2', 'b', 'c'),
    ];
    const out = layoutGraph(nodes, edges);
    const sub = nodeRect(find(out, 'sub'));
    const subStyle = find(out, 'sub').style as { width: number; height: number };

    for (const id of ['a', 'b', 'c']) {
      const c = nodeRect(find(out, id));
      // 子节点在容器内：相对坐标非负且右/下边界不越界
      expect(c.x).toBeGreaterThanOrEqual(0);
      expect(c.y).toBeGreaterThanOrEqual(0);
      expect(c.x + c.w).toBeLessThanOrEqual(subStyle.width);
      expect(c.y + c.h).toBeLessThanOrEqual(subStyle.height);
    }
    // 容器尺寸被内容撑开，而不是维持初始 260x140
    expect(subStyle.width).toBeGreaterThanOrEqual(180);
    expect(subStyle.height).toBeGreaterThan(140);
    // 容器本身坐标有效
    expect(Number.isFinite(sub.x)).toBe(true);
  });

  it('嵌套容器：pipeline 包裹 sub，sub 包裹 task', () => {
    const nodes = [
      makeNode('__pipeline__', 'editorPipeline', { style: { width: 600, height: 300 } }),
      makeNode('sub', 'editorSubPipeline', { parentId: '__pipeline__' }),
      makeNode('a', 'editorTask', { parentId: 'sub' }),
      makeNode('b', 'editorTask', { parentId: 'sub' }),
    ];
    const edges = [makeEdge('e1', 'a', 'b')];
    const out = layoutGraph(nodes, edges);
    const pStyle = find(out, '__pipeline__').style as { width: number; height: number };
    const sub = nodeRect(find(out, 'sub'));
    const subStyle = find(out, 'sub').style as { width: number; height: number };
    const a = nodeRect(find(out, 'a'));

    // sub 落在 pipeline 内
    expect(sub.x).toBeGreaterThanOrEqual(0);
    expect(sub.y).toBeGreaterThanOrEqual(0);
    expect(sub.x + subStyle.width).toBeLessThanOrEqual(pStyle.width);
    expect(sub.y + subStyle.height).toBeLessThanOrEqual(pStyle.height);
    // task 落在 sub 内（相对 sub 的坐标）
    expect(a.x).toBeGreaterThanOrEqual(0);
    expect(a.y).toBeGreaterThanOrEqual(0);
    expect(a.x + a.w).toBeLessThanOrEqual(subStyle.width);
    expect(a.y + a.h).toBeLessThanOrEqual(subStyle.height);
  });

  it('editorTask 作为容器时也包裹其原子子节点', () => {
    const nodes = [
      makeNode('task', 'editorTask', { style: { width: 180, height: 56 } }),
      makeNode('atomic', 'editorTask', { parentId: 'task' }),
    ];
    const out = layoutGraph(nodes, []);
    const tStyle = find(out, 'task').style as { width: number; height: number };
    const atomic = nodeRect(find(out, 'atomic'));
    expect(atomic.x).toBeGreaterThanOrEqual(0);
    expect(atomic.y).toBeGreaterThanOrEqual(0);
    expect(atomic.x + atomic.w).toBeLessThanOrEqual(tStyle.width);
    expect(atomic.y + atomic.h).toBeLessThanOrEqual(tStyle.height);
  });

  it('无内部边的子节点纵向堆叠且不重叠（post 子节点场景）', () => {
    const nodes = [
      makeNode('post', 'editorPostParent', { style: { width: 280, height: 150 } }),
      makeNode('c1', 'editorPostChild', { parentId: 'post' }),
      makeNode('c2', 'editorPostChild', { parentId: 'post' }),
    ];
    const out = layoutGraph(nodes, []);
    const c1 = nodeRect(find(out, 'c1'));
    const c2 = nodeRect(find(out, 'c2'));
    // 纵向排列：y 不同
    expect(c1.y).not.toBe(c2.y);
    // 矩形不相交
    const overlap =
      c1.x < c2.x + c2.w && c2.x < c1.x + c1.w && c1.y < c2.y + c2.h && c2.y < c1.y + c1.h;
    expect(overlap).toBe(false);
    // 父容器包裹两者
    const pStyle = find(out, 'post').style as { width: number; height: number };
    for (const c of [c1, c2]) {
      expect(c.x + c.w).toBeLessThanOrEqual(pStyle.width);
      expect(c.y + c.h).toBeLessThanOrEqual(pStyle.height);
    }
  });
});

describe('layoutGraph — 跨容器与方向', () => {
  it('build → deploy 跨容器依赖：deploy 在 build 下方且容器不重叠', () => {
    const nodes = [
      makeNode('__pipeline__', 'editorPipeline', { style: { width: 800, height: 400 } }),
      makeNode('build', 'editorSubPipeline', { parentId: '__pipeline__' }),
      makeNode('ba', 'editorTask', { parentId: 'build' }),
      makeNode('deploy', 'editorSubPipeline', { parentId: '__pipeline__' }),
      makeNode('da', 'editorTask', { parentId: 'deploy' }),
    ];
    const edges = [makeEdge('e1', 'build', 'deploy')];
    const out = layoutGraph(nodes, edges);
    const build = nodeRect(find(out, 'build'));
    const deploy = nodeRect(find(out, 'deploy'));
    const buildStyle = find(out, 'build').style as { width: number; height: number };
    const deployStyle = find(out, 'deploy').style as { width: number; height: number };
    expect(deploy.y).toBeGreaterThan(build.y);
    const overlap =
      build.x < deploy.x + deployStyle.width &&
      deploy.x < build.x + buildStyle.width &&
      build.y < deploy.y + deployStyle.height &&
      deploy.y < build.y + buildStyle.height;
    expect(overlap).toBe(false);
  });

  it('容器内边与跨容器边混合：task 级边不影响容器层方向', () => {
    const nodes = [
      makeNode('subA', 'editorSubPipeline', { style: { width: 260, height: 140 } }),
      makeNode('a1', 'editorTask', { parentId: 'subA' }),
      makeNode('a2', 'editorTask', { parentId: 'subA' }),
      makeNode('subB', 'editorSubPipeline', { style: { width: 260, height: 140 } }),
      makeNode('b1', 'editorTask', { parentId: 'subB' }),
    ];
    const edges = [
      makeEdge('e1', 'a1', 'a2'),
      makeEdge('e2', 'subA', 'subB'),
    ];
    const out = layoutGraph(nodes, edges);
    const subA = nodeRect(find(out, 'subA'));
    const subB = nodeRect(find(out, 'subB'));
    const a1 = nodeRect(find(out, 'a1'));
    const a2 = nodeRect(find(out, 'a2'));
    expect(subB.y).toBeGreaterThan(subA.y);
    expect(a2.y).toBeGreaterThan(a1.y);
  });
});

describe('layoutGraph — 确定性与健壮性', () => {
  it('同输入两次布局结果完全一致（消除布局跳动）', () => {
    const nodes = [
      makeNode('__pipeline__', 'editorPipeline', {}),
      makeNode('s1', 'editorSubPipeline', { parentId: '__pipeline__' }),
      makeNode('t1', 'editorTask', { parentId: 's1' }),
      makeNode('t2', 'editorTask', { parentId: 's1' }),
      makeNode('s2', 'editorSubPipeline', { parentId: '__pipeline__' }),
      makeNode('t3', 'editorTask', { parentId: 's2' }),
    ];
    const edges = [makeEdge('e1', 's1', 's2'), makeEdge('e2', 't1', 't2')];
    const first = layoutGraph(nodes, edges);
    const second = layoutGraph(nodes, edges);
    const positions = (ns: Node[]) =>
      ns.map((n) => ({ id: n.id, x: n.position.x, y: n.position.y, style: n.style ?? null }));
    expect(positions(first)).toEqual(positions(second));
  });

  it('依赖不存在节点的孤儿边被忽略，不影响布局', () => {
    const nodes = [makeNode('a', 'editorTask'), makeNode('b', 'editorTask')];
    const edges = [makeEdge('e1', 'ghost', 'a'), makeEdge('e2', 'a', 'b')];
    const out = layoutGraph(nodes, edges);
    const a = nodeRect(find(out, 'a'));
    const b = nodeRect(find(out, 'b'));
    expect(b.y).toBeGreaterThan(a.y);
  });

  it('未测量节点使用默认尺寸，无 NaN', () => {
    const nodes = [makeNode('a', 'editorTask'), makeNode('b', 'editorPostChild')];
    const out = layoutGraph(nodes, []);
    for (const n of out) {
      expect(Number.isFinite(n.position.x)).toBe(true);
      expect(Number.isFinite(n.position.y)).toBe(true);
    }
  });

  it('折叠容器保持折叠尺寸，不被子节点撑开（布局不递归内部）', () => {
    const nodes = [
      makeNode('sub', 'editorSubPipeline', {
        style: { width: 140, height: 48 },
        data: { collapsed: true },
      }),
      makeNode('a', 'editorTask', { parentId: 'sub' }),
      makeNode('b', 'editorTask', { parentId: 'sub' }),
    ];
    const out = layoutGraph(nodes, []);
    const sub = out.find((n) => n.id === 'sub')!;
    // 折叠尺寸原样保留，而不是按两个子节点重算成大容器
    expect(sub.style).toMatchObject({ width: 140, height: 48 });
  });

  it('父容器 id 指向不存在的节点时按根层节点处理', () => {
    const nodes = [makeNode('a', 'editorTask', { parentId: 'ghost' })];
    const out = layoutGraph(nodes, []);
    expect(Number.isFinite(out[0].position.x)).toBe(true);
  });
});
