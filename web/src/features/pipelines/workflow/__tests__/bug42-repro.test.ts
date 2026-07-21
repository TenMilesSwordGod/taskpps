import { describe, it, expect } from 'vitest';
import { findDropParentContext, validateDrop } from '../validateDrop';
import type { Node } from '@xyflow/react';
import type { EditorNodeData } from '../yamlToNodes';

/**
 * Bug #42 深入重现场景：
 * 用真实的 CSS 尺寸（Task 180x56，SubPipeline 260x140+）模拟拖放到 Task 内
 * 验证 findDropParentContext 在各种条件下都能正确检测到 Task 容器
 */

/** 模拟一个 SubPipeline 节点（有 style，ReactFlow 直接使用 style 尺寸） */
function makeSubPipeline(overrides: Partial<Node<EditorNodeData>> = {}): Node<EditorNodeData> {
  return {
    id: 'sp1',
    type: 'editorSubPipeline',
    position: { x: 100, y: 100 },
    style: { width: 300, height: 250 },
    width: 300,
    height: 250,
    data: { label: 'Sub' },
    ...overrides,
  } as Node<EditorNodeData>;
}

/** 模拟一个 Task 容器节点（无 style，依靠 DOM 测量，所以直接用 width/height） */
function makeTask(overrides: Partial<Node<EditorNodeData>> = {}): Node<EditorNodeData> {
  return {
    id: 'task1',
    type: 'editorTask',
    position: { x: 40, y: 60 },
    width: 180,  // 对应 EditorTaskNode CSS width: 180
    height: 56,  // 对应 EditorTaskNode CSS minHeight: 56
    data: { label: 'myTask', task: { name: 'myTask', env: {}, retry: 0, depends_on: [] }, taskType: 'command' },
    ...overrides,
  } as Node<EditorNodeData>;
}

describe('Bug#42 repro: SubPipeline 内嵌 Task 时原子行为拖放检测', () => {

  it('Task 根级（无父容器）且落点在其内部 → task 上下文', () => {
    const task = makeTask({ id: 't1', position: { x: 0, y: 0 } });
    const nodes = [task];
    // 落点 (90, 28) 在 Task (0,0)-(180,56) 内部
    const result = findDropParentContext({ x: 90, y: 28 }, nodes);
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });

  it('SubPipeline 包含 Task，落点 Task 正中心 → task 上下文', () => {
    const sub = makeSubPipeline({ id: 'sp1', position: { x: 100, y: 100 } });
    const task = makeTask({
      id: 't1',
      parentId: 'sp1',
      position: { x: 40, y: 60 },
    });
    const nodes = [sub, task];
    // Task 绝对范围: (140, 160) - (320, 216)
    // 落点 (200, 180) 在 Task 内部 → 应检测为 task
    const result = findDropParentContext({ x: 200, y: 180 }, nodes);
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });

  it('SubPipeline 包含 Task，落点在 Task 内但在 SubPipeline 边界附近 → task 上下文', () => {
    const sub = makeSubPipeline({ id: 'sp1', position: { x: 100, y: 100 } });
    const task = makeTask({
      id: 't1',
      parentId: 'sp1',
      position: { x: 40, y: 60 },
    });
    const nodes = [sub, task];
    // Task 绝对范围: (140, 160) - (320, 216)
    // 落点在 Task 左上角附近 (145, 165)
    const result = findDropParentContext({ x: 145, y: 165 }, nodes);
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });

  it('SubPipeline 包含 Task，落点在 Task 的最下边缘 → task 上下文', () => {
    const sub = makeSubPipeline({ id: 'sp1', position: { x: 100, y: 100 } });
    const task = makeTask({
      id: 't1',
      parentId: 'sp1',
      position: { x: 40, y: 60 },
    });
    const nodes = [sub, task];
    // Task 绝对范围: y: 160-216
    // 落点 (200, 215) - 在最下边缘
    const result = findDropParentContext({ x: 200, y: 215 }, nodes);
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });

  it('SubPipeline 包含 Task，落点刚好在 Task 外但在 SubPipeline 内 → subpipeline 上下文', () => {
    const sub = makeSubPipeline({ id: 'sp1', position: { x: 100, y: 100 } });
    const task = makeTask({
      id: 't1',
      parentId: 'sp1',
      position: { x: 40, y: 60 },
    });
    const nodes = [sub, task];
    // Task 绝对范围: x: 140-320, y: 160-216
    // 落点 (330, 180) - 在 Task 右侧外部，但仍在 SubPipeline 内部
    const result = findDropParentContext({ x: 330, y: 180 }, nodes);
    expect(result.context).toBe('subpipeline');
    expect(result.parentId).toBe('sp1');
  });

  it('原子节点落入 Task 时 validateDrop 应放行（R7）', () => {
    const task = makeTask({ id: 't1', position: { x: 0, y: 0 } });
    const nodes = [task];
    const ctx = findDropParentContext({ x: 90, y: 28 }, nodes);
    expect(ctx.context).toBe('task');
    // 验证 4 种原子类型都放行
    for (const atomicType of ['task_atomic_cmd', 'task_atomic_step', 'task_atomic_plugin', 'task_atomic_invoke']) {
      const error = validateDrop(atomicType, ctx.context, nodes);
      expect(error).toBeNull();
    }
  });

  it('原子节点落入 SubPipeline（非 Task 内）时 validateDrop 应拒绝（R5）', () => {
    const sub = makeSubPipeline({ id: 'sp1', position: { x: 100, y: 100 } });
    const task = makeTask({
      id: 't1',
      parentId: 'sp1',
      position: { x: 40, y: 60 },
    });
    const nodes = [sub, task];
    // 落点在 SubPipeline 内但 Task 外
    const ctx = findDropParentContext({ x: 150, y: 130 }, nodes);
    expect(ctx.context).toBe('subpipeline');
    for (const atomicType of ['task_atomic_cmd', 'task_atomic_step', 'task_atomic_plugin', 'task_atomic_invoke']) {
      const error = validateDrop(atomicType, ctx.context, nodes);
      expect(error).toContain('原子行为节点不可直接放入 SubPipeline 根层级');
    }
  });

  it('多级嵌套: Pipeline > SubPipeline > Task，落点在 Task 内 → task 上下文', () => {
    const pipeline = {
      id: '__pipeline__',
      type: 'editorPipeline',
      position: { x: 0, y: 0 },
      style: { width: 800, height: 400 },
      width: 800,
      height: 400,
      data: { label: 'Root' },
    } as Node<EditorNodeData>;

    const sub = makeSubPipeline({
      id: 'sp1',
      parentId: '__pipeline__',
      position: { x: 50, y: 50 },
    });

    const task = makeTask({
      id: 't1',
      parentId: 'sp1',
      position: { x: 40, y: 60 },
    });

    const nodes = [pipeline, sub, task];

    // Task 绝对坐标:
    //   pipeline(0,0) → sub(50,50) → task(40,60)
    //   绝对 = (50+40, 50+60) = (90, 110)
    //   绝对范围: x: 90-270, y: 110-166
    const result = findDropParentContext({ x: 150, y: 130 }, nodes);
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });

  it('Task 高度因内容撑开（实测 80px）时落点检测仍正确', () => {
    const sub = makeSubPipeline({ id: 'sp1', position: { x: 100, y: 100 } });
    const task = makeTask({
      id: 't1',
      parentId: 'sp1',
      position: { x: 40, y: 60 },
      height: 80,  // 内容较多时撑高
    });
    const nodes = [sub, task];
    // Task 绝对范围: x: 140-320, y: 160-240
    const result = findDropParentContext({ x: 200, y: 230 }, nodes);
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });

  it('当已经存在原子节点在 Task 内，新落点在旧原子节点范围外但 Task 内 → task 上下文（检测到 Task 而非旧原子节点）', () => {
    const sub = makeSubPipeline({ id: 'sp1', position: { x: 100, y: 100 } });
    const task = makeTask({
      id: 't1',
      parentId: 'sp1',
      position: { x: 40, y: 60 },
      width: 180,
      height: 120,  // 较大以容纳原子节点
    });
    // 已有原子节点在 Task 内部（子节点，type 也是 editorTask）
    const existingAtomic = makeTask({
      id: 'atomic1',
      parentId: 't1',
      position: { x: 10, y: 10 },
      width: 160,
      height: 40,
      data: { label: 'CMD', task: { name: 'CMD', env: {}, retry: 0, depends_on: [] }, taskType: 'command' },
    });
    const nodes = [sub, task, existingAtomic];

    // 落点在 Task 内但不在已有原子节点内（(150, 80) 在 Task 绝对范围内，但在原子节点绝对范围外）
    // 原子绝对范围: x: (140+10=150) ~ (150+160=310), y: (160+10=170) ~ (170+40=210)
    // Task 绝对范围: x: 140-320, y: 160-280
    // 落点 (200, 240) - 在 Task 内但不在原子节点内
    const result = findDropParentContext({ x: 200, y: 240 }, nodes);
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });

  it('当已经存在原子节点在 Task 内，新落点在旧原子节点范围内 → 应返回 Task 容器而非旧原子节点（原子节点不应作为容器）', () => {
    const sub = makeSubPipeline({ id: 'sp1', position: { x: 100, y: 100 } });
    const task = makeTask({
      id: 't1',
      parentId: 'sp1',
      position: { x: 40, y: 60 },
      width: 180,
      height: 120,
    });
    // 已有原子节点在 Task 内部
    const existingAtomic = makeTask({
      id: 'atomic1',
      parentId: 't1',
      position: { x: 10, y: 10 },
      width: 160,
      height: 40,
      data: { label: 'CMD', taskType: 'command' },
    });
    const nodes = [sub, task, existingAtomic];

    // 原子绝对范围: x: (140+10=150) ~ (150+160=310), y: (160+10=170) ~ (170+40=210)
    // 落点 (200, 190) - 在原子节点范围内
    const result = findDropParentContext({ x: 200, y: 190 }, nodes);
    // 期望：返回 Task 容器，而不是返回原子节点作为 'task' 上下文
    // 因为原子节点是叶子节点不应作为容器，应该向上返回 Task
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });
});
