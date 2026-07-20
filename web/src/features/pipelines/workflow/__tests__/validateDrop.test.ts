import { describe, it, expect } from 'vitest';
import { validateDrop, findDropParentContext } from '../validateDrop';
import type { Node } from '@xyflow/react';
import type { EditorNodeData } from '../yamlToNodes';

/**
 * handleDrop 容器嵌套校验规则测试
 * 共 6 条规则（R1-R6），逐条覆盖
 */

function makeNode(overrides: Partial<Node<EditorNodeData>> = {}): Node<EditorNodeData> {
  return {
    id: 'n1',
    type: 'editorTask',
    position: { x: 0, y: 0 },
    data: {},
    ...overrides,
  } as Node<EditorNodeData>;
}

describe('R1: SubPipeline 不可嵌套 SubPipeline', () => {
  it('根级拖入 SubPipeline 应通过', () => {
    expect(validateDrop('subpipeline', 'canvas-root', [])).toBeNull();
  });

  it('SubPipeline 内部拖入 SubPipeline 应拒绝', () => {
    const result = validateDrop('subpipeline', 'subpipeline', []);
    expect(result).toContain('SubPipeline 不可嵌套在另一个 SubPipeline 内部');
  });

  it('Post 父容器内部拖入 SubPipeline 应拒绝', () => {
    const result = validateDrop('subpipeline', 'post_parent', []);
    expect(result).toContain('Post 子容器内部不可嵌套其它容器节点');
  });
});

describe('R2: Post 父容器仅可在根层级', () => {
  it('根级拖入 Post 父容器应通过', () => {
    expect(validateDrop('post_parent', 'canvas-root', [])).toBeNull();
  });

  it('SubPipeline 内部拖入 Post 父容器应拒绝', () => {
    // R2 先于 R5 触发：post_parent 在任何非根级都会拒绝
    const result = validateDrop('post_parent', 'subpipeline', []);
    expect(result).not.toBeNull();
    expect(result).toContain('Post 父容器仅可放置在根层级');
  });
});

describe('R3: Post 子容器各类型最多 1 个', () => {
  it('无同类型 post_child 时通过', () => {
    expect(validateDrop('post_child_on_fail', 'canvas-root', [])).toBeNull();
  });

  it('on_fail 已存在时应拒绝新的 on_fail', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({ type: 'editorPostChild', data: { postVariant: 'on_fail' } }),
    ];
    const result = validateDrop('post_child_on_fail', 'canvas-root', nodes);
    expect(result).toContain('on_fail 已存在');
  });

  it('on_success 已存在时应拒绝新的 on_success', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({ type: 'editorPostChild', data: { postVariant: 'on_success' } }),
    ];
    const result = validateDrop('post_child_on_success', 'canvas-root', nodes);
    expect(result).toContain('on_success 已存在');
  });

  it('always 已存在时应拒绝新的 always', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({ type: 'editorPostChild', data: { postVariant: 'always' } }),
    ];
    const result = validateDrop('post_child_always', 'canvas-root', nodes);
    expect(result).toContain('always 已存在');
  });

  it('不同类型 post_child 可共存', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({ type: 'editorPostChild', data: { postVariant: 'on_fail' } }),
    ];
    expect(validateDrop('post_child_on_success', 'canvas-root', nodes)).toBeNull();
    expect(validateDrop('post_child_always', 'canvas-root', nodes)).toBeNull();
  });
});

describe('R4: Post 子容器不可嵌套其它容器', () => {
  it('Task 类型拖入 post_parent 应拒绝', () => {
    const result = validateDrop('task', 'post_parent', []);
    expect(result).toContain('不可嵌套其它容器节点');
  });

  it('SubPipeline 类型拖入 post_parent 应拒绝', () => {
    const result = validateDrop('subpipeline', 'post_parent', []);
    expect(result).toContain('不可嵌套其它容器节点');
  });

  it('post_child 拖入 post_parent 应通过', () => {
    // post_child 前缀匹配
    expect(validateDrop('post_child_on_fail', 'post_parent', [])).toBeNull();
    expect(validateDrop('post_child_on_success', 'post_parent', [])).toBeNull();
    expect(validateDrop('post_child_always', 'post_parent', [])).toBeNull();
  });
});

describe('R5: 原子行为节点不可直接放入 SubPipeline', () => {
  it('cmd 原子节点放入 subpipeline 应拒绝', () => {
    const result = validateDrop('task_atomic_cmd', 'subpipeline', []);
    expect(result).toContain('原子行为节点不可直接放入 SubPipeline 根层级');
  });

  it('step 原子节点放入 subpipeline 应拒绝', () => {
    const result = validateDrop('task_atomic_step', 'subpipeline', []);
    expect(result).toContain('原子行为节点不可直接放入 SubPipeline 根层级');
  });

  it('plugin 原子节点放入 subpipeline 应拒绝', () => {
    const result = validateDrop('task_atomic_plugin', 'subpipeline', []);
    expect(result).toContain('原子行为节点不可直接放入 SubPipeline 根层级');
  });

  it('invoke 原子节点放入 subpipeline 应拒绝', () => {
    const result = validateDrop('task_atomic_invoke', 'subpipeline', []);
    expect(result).toContain('原子行为节点不可直接放入 SubPipeline 根层级');
  });

  it('Task 容器放入 subpipeline 应通过', () => {
    expect(validateDrop('task', 'subpipeline', [])).toBeNull();
  });
});

describe('R6: Start/End 节点唯一性', () => {
  it('无 Start/End 时可拖入', () => {
    const nodesWithoutStartEnd = [
      makeNode({ id: 'other', type: 'editorSubPipeline' }),
    ];
    expect(validateDrop('startend', 'canvas-root', nodesWithoutStartEnd)).toBeNull();
  });

  it('已有 Start 和 End 时拒绝', () => {
    const nodesWithBoth = [
      makeNode({ id: '__start__', type: 'editorStartEnd', data: { variant: 'start' } }),
      makeNode({ id: '__end__', type: 'editorStartEnd', data: { variant: 'end' } }),
    ];
    const result = validateDrop('startend', 'canvas-root', nodesWithBoth);
    expect(result).toContain('已有 Start 和 End 节点');
  });
});

describe('边界场景', () => {
  it('canvas-root 中拖入 task 应通过', () => {
    expect(validateDrop('task', 'canvas-root', [])).toBeNull();
  });

  it('未知类型在 canvas-root 中应通过（不在限制列表中）', () => {
    // 如 'startend' 会被 R6 检查，但没有 start/end 时通过
    expect(validateDrop('some_unknown', 'canvas-root', [])).toBeNull();
  });

  it('post_child 类型在 canvas-root 无重复时通过', () => {
    expect(validateDrop('post_child_always', 'canvas-root', [])).toBeNull();
  });
});

// v2 (2026-07): findDropParentContext 测试 — 动态 parentContext 计算
describe('findDropParentContext: 动态计算 drop 位置下的父容器', () => {
  it('drop 在空画布上 → canvas-root', () => {
    const result = findDropParentContext({ x: 100, y: 100 }, []);
    expect(result.context).toBe('canvas-root');
    expect(result.parentId).toBeUndefined();
  });

  it('drop 在 SubPipeline 节点内部 → subpipeline', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({
        id: 'sp1',
        type: 'editorSubPipeline',
        position: { x: 0, y: 0 },
        width: 260,
        height: 140,
      }),
    ];
    const result = findDropParentContext({ x: 50, y: 50 }, nodes);
    expect(result.context).toBe('subpipeline');
    expect(result.parentId).toBe('sp1');
  });

  it('drop 在 Post 父容器节点内部 → post_parent', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({
        id: 'pp1',
        type: 'editorPostParent',
        position: { x: 100, y: 100 },
        width: 280,
        height: 150,
      }),
    ];
    const result = findDropParentContext({ x: 200, y: 150 }, nodes);
    expect(result.context).toBe('post_parent');
    expect(result.parentId).toBe('pp1');
  });

  it('drop 在 SubPipeline 边界外 → canvas-root', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({
        id: 'sp1',
        type: 'editorSubPipeline',
        position: { x: 0, y: 0 },
        width: 260,
        height: 140,
      }),
    ];
    const result = findDropParentContext({ x: 300, y: 50 }, nodes);
    expect(result.context).toBe('canvas-root');
    expect(result.parentId).toBeUndefined();
  });

  it('drop 在 Task 节点内部 → canvas-root（Task 非容器）', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({
        id: 't1',
        type: 'editorTask',
        position: { x: 0, y: 0 },
        width: 180,
        height: 56,
      }),
    ];
    const result = findDropParentContext({ x: 50, y: 25 }, nodes);
    expect(result.context).toBe('canvas-root');
    expect(result.parentId).toBeUndefined();
  });

  it('节点未测量（width/height 为 undefined）时跳过 → canvas-root', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({
        id: 'sp1',
        type: 'editorSubPipeline',
        position: { x: 0, y: 0 },
        width: undefined,
        height: undefined,
      }),
    ];
    const result = findDropParentContext({ x: 0, y: 0 }, nodes);
    expect(result.context).toBe('canvas-root');
    expect(result.parentId).toBeUndefined();
  });

  it('多个容器节点重叠时返回最先匹配的 SubPipeline', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeNode({
        id: 'sp1',
        type: 'editorSubPipeline',
        position: { x: 0, y: 0 },
        width: 300,
        height: 200,
      }),
      makeNode({
        id: 'sp2',
        type: 'editorSubPipeline',
        position: { x: 50, y: 50 },
        width: 300,
        height: 200,
      }),
    ];
    // 在 sp1 内部但也在 sp2 内部 → 返回 sp1（先匹配）
    const result = findDropParentContext({ x: 100, y: 100 }, nodes);
    expect(result.context).toBe('subpipeline');
    expect(result.parentId).toBe('sp1');
  });
});
