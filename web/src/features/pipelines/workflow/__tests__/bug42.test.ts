import { describe, it, expect } from 'vitest';
import { findDropParentContext, validateDrop } from '../validateDrop';
import type { Node } from '@xyflow/react';
import type { EditorNodeData } from '../yamlToNodes';

/**
 * Bug #42 回归测试：findDropParentContext 正确识别 editorTask 容器。
 *
 * 修复后行为：原子节点（CMD/STEP/PLUGIN/INVOKE）拖入 Task 容器内时，
 * findDropParentContext 返回 { context: 'task', parentId: <taskId> }，
 * validateDrop 放行原子节点落入 Task（R7）。
 */

function makeTaskNode(overrides: Partial<Node<EditorNodeData>> = {}): Node<EditorNodeData> {
  return {
    id: 'task1',
    type: 'editorTask',
    position: { x: 100, y: 100 },
    width: 260,
    height: 120,
    data: { label: 'myTask' },
    ...overrides,
  } as Node<EditorNodeData>;
}

describe('Bug#42 (RED) findDropParentContext 应识别 Task 容器', () => {
  it('根级 Task 容器内部落点应返回 task 上下文 —— 当前错误返回 canvas-root', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeTaskNode({ id: 't1', position: { x: 0, y: 0 }, width: 200, height: 80 }),
    ];
    // 落点在 Task 内部 (50, 40)
    const result = findDropParentContext({ x: 50, y: 40 }, nodes);

    // 期望：Task 是合法容器，应返回 task 上下文
    // 实际：Task 被跳过，返回 { context: 'canvas-root', parentId: undefined }
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });

  it('SubPipeline 内嵌 Task 时落点应在 Task 上下文 —— 当前错误落入外层 SubPipeline', () => {
    const sp: Node<EditorNodeData> = {
      id: 'sp1',
      type: 'editorSubPipeline',
      position: { x: 0, y: 0 },
      width: 500,
      height: 400,
      data: { label: 'sub' },
    };
    // Task 作为 SubPipeline 的子节点，position 相对父节点
    // 相对 (50,50) => 绝对 (50, 50)；尺寸 200x80 => 绝对范围 (50~250, 50~130)
    const task: Node<EditorNodeData> = {
      id: 't1',
      type: 'editorTask',
      parentId: 'sp1',
      position: { x: 50, y: 50 },
      width: 200,
      height: 80,
      data: { label: 'myTask' },
    };
    const nodes = [sp, task];

    // 绝对落点 (100, 80) 在 Task 绝对范围 (50~250, 50~130) 内
    const result = findDropParentContext({ x: 100, y: 80 }, nodes);

    // 期望：Task 是子节点的合法容器，应优先返回 task 上下文
    // 实际：Task 被跳过，落入外层 SubPipeline → { context: 'subpipeline', parentId: 'sp1' }
    expect(result.context).toBe('task');
    expect(result.parentId).toBe('t1');
  });

  it('原子节点落入 Task 时 validateDrop 应通过 —— 当前因上下文不正确而误拒', () => {
    const nodes: Node<EditorNodeData>[] = [
      makeTaskNode({ id: 't1', position: { x: 0, y: 0 }, width: 200, height: 80 }),
    ];
    const ctx = findDropParentContext({ x: 50, y: 40 }, nodes);

    // 若 findDropParentContext 正确返回 task 上下文，则 R5 应放行
    // 当前因返回 canvas-root，原子节点进入 R5 时 root 层级无限制 → 实际通过
    // 但如果 Task 在 SubPipeline 内，ctx 返回 subpipeline 则 R5 会误拒
    // 这里用 task 上下文模拟正确流转：validateDrop 需要支持 'task' 上下文
    const error = validateDrop('task_atomic_cmd', ctx.context, nodes);
    expect(error).toBeNull();
  });
});
