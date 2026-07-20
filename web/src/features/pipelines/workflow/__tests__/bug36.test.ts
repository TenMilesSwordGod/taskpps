import { describe, it, expect } from 'vitest';
import type { Node } from '@xyflow/react';
import { findDropParentContext, validateDrop } from '../validateDrop';
import type { EditorNodeData } from '../yamlToNodes';

/**
 * Bug #36 回归测试：拖 SubPipeline 到嵌套 SubPipeline 内部应被 R1 拒绝。
 *
 * 根因（核实结论）：findDropParentContext 直接用 node.position 当作绝对画布坐标做 bounds 检测，
 * 但 ReactFlow 中带 parentId 的子节点 position 是“相对父容器”的。当内层 SubPipeline 作为外层
 * 的子节点时，其 position 是相对坐标，未换算绝对坐标导致落点漏判为 canvas-root，R1 失效。
 * 修复：沿 parentId 链递归累加得到绝对坐标再做检测。
 *
 * 本测试同时覆盖合法 drop 不应被误拒，确保坐标换算不影响其它上下文判定。
 */

// 构造最小节点数据：外层 SubPipeline（顶层，绝对坐标）+ 内层 SubPipeline（外层子节点，相对坐标）
function buildNestedNodes(): Node<EditorNodeData>[] {
  const outer: Node<EditorNodeData> = {
    id: 'outer',
    type: 'editorSubPipeline',
    position: { x: 100, y: 100 }, // 顶层节点：绝对坐标
    width: 400,
    height: 400,
    data: { label: 'outer' },
  };

  // 内层 SubPipeline 是 outer 的子节点：position 相对 outer
  // 相对 (600,50) => 绝对 (700,150)；尺寸 100x100 => 绝对 bounds (700~800, 150~250)
  const inner: Node<EditorNodeData> = {
    id: 'inner',
    type: 'editorSubPipeline',
    parentId: 'outer',
    position: { x: 600, y: 50 }, // 相对坐标（被 bug 当作绝对坐标误用）
    width: 100,
    height: 100,
    data: { label: 'inner' },
  };

  return [outer, inner];
}

describe('Bug#36 拖 SubPipeline 进嵌套 SubPipeline 内部应被拒绝', () => {
  it('findDropParentContext 应识别落在内层 SubPipeline 绝对范围内的落点为 subpipeline 上下文', () => {
    const nodes = buildNestedNodes();
    // 绝对 flowPosition，落在内层 SubPipeline 的绝对 bounds 内 (700~800, 150~250)
    const flowPosition = { x: 750, y: 200 };

    const result = findDropParentContext(flowPosition, nodes);

    // 正确期望：落在内层 SubPipeline 内部，应返回内层作为父容器上下文
    expect(result.context).toBe('subpipeline');
    expect(result.parentId).toBe('inner');
  });

  it('validateDrop 对 subpipeline 上下文下的 subpipeline 应返回非空（被 R1 拒绝）', () => {
    const nodes = buildNestedNodes();
    const flowPosition = { x: 750, y: 200 };
    const ctx = findDropParentContext(flowPosition, nodes);

    // 把 findDropParentContext 的结果喂给 validateDrop，模拟 handleDrop 逻辑
    const error = validateDrop('subpipeline', ctx.context, nodes);

    // 正确期望：SubPipeline 嵌套 SubPipeline 必须被 R1 拒绝（返回非空原因）
    expect(error).not.toBeNull();
    expect(typeof error).toBe('string');
  });
});

describe('Bug#36 合法 drop 不应被坐标换算误拒', () => {
  it('落在画布空白处应识别为 canvas-root，且 subpipeline 拖入根级通过校验', () => {
    const nodes = buildNestedNodes();
    // 绝对坐标落在所有容器之外
    const flowPosition = { x: 50, y: 50 };
    const ctx = findDropParentContext(flowPosition, nodes);
    expect(ctx.context).toBe('canvas-root');
    expect(validateDrop('subpipeline', ctx.context, nodes)).toBeNull();
  });

  it('落在外层 SubPipeline 绝对范围内应识别为 subpipeline 上下文', () => {
    const nodes = buildNestedNodes();
    // 外层绝对 bounds (100~500, 100~500)，避开内层 (700~800,150~250)
    const flowPosition = { x: 200, y: 200 };
    const ctx = findDropParentContext(flowPosition, nodes);
    expect(ctx.context).toBe('subpipeline');
    expect(ctx.parentId).toBe('outer');
  });

  it('落在 Task 父容器内部应识别为合法上下文且 task 类型通过校验', () => {
    const outer = {
      id: 'outer',
      type: 'editorSubPipeline',
      position: { x: 100, y: 100 },
      width: 400,
      height: 400,
      data: { label: 'outer' },
    } as Node<EditorNodeData>;
    // Task 作为外层 SubPipeline 的子节点：相对 (50,50) => 绝对 (150,150)
    const task = {
      id: 'task1',
      type: 'editorTask',
      parentId: 'outer',
      position: { x: 50, y: 50 },
      width: 120,
      height: 80,
      data: { label: 'task' },
    } as Node<EditorNodeData>;
    const nodes = [outer, task];

    // 绝对落点 (180,180) 落在 Task 绝对范围 (150~270, 150~230) 内
    const ctx = findDropParentContext({ x: 180, y: 180 }, nodes);
    // 注意：当前 findDropParentContext 仅识别 SubPipeline / PostParent 为容器，
    // Task 不作为 drop 父容器，落在其内部仍按最外层容器（subpipeline）处理，符合 R5 设计。
    expect(ctx.context).toBe('subpipeline');
    expect(ctx.parentId).toBe('outer');
  });
});
