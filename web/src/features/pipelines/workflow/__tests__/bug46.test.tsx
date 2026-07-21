/**
 * Bug #46 RED 测试 — 自适应窗口/布局按钮造成子节点位置错乱
 *
 * 复现步骤：在 Pipeline 编辑器中编排混合布局（task + pipeline + subpipeline），
 * 点击工具栏"布局"按钮 → 子节点（有 parentId）的 position 为 dagre 输出的绝对坐标，
 * 但 ReactFlow 将其按相对父容器的偏移解释，导致节点"到处乱飞"。
 *
 * 根因：handleAutoLayout 调用 applyDagreLayout 后直接将 dagre 的绝对坐标
 * 赋值给所有节点，未将子节点（有 parentId）的 position 转换为相对父容器的偏移。
 *
 * RED 测试策略：
 *   1. mock applyDagreLayout 返回已知绝对坐标
 *   2. 点击布局按钮触发 handleAutoLayout（fix 后含转换逻辑）
 *   3. 通过 onGraphChange 回调断言子节点（有 parentId）的 position 已转为
 *      相对父容器的偏移（小值），而非 dagre 的绝对大值
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkflowEditor from '../WorkflowEditor';
import type { Node } from '@xyflow/react';

// mock dagreLayout 以精确控制返回的绝对坐标
vi.mock('@/utils/dagreLayout', () => ({
  applyDagreLayout: vi.fn(),
}));

import { applyDagreLayout } from '@/utils/dagreLayout';

describe('Bug #46 — 自动布局后子节点 position 应为相对父容器的偏移', () => {
  it('RED: 布局后子节点（有 parentId）的 position 应为相对父容器的偏移', async () => {
    // 模拟 dagre 布局返回的绝对坐标（dagre 对所有节点一视同仁，输出 canvas 级绝对坐标）
    const dagreOutput: Node[] = [
      { id: '__start__', position: { x: 75, y: 0 }, data: {} },
      { id: '__pipeline__', position: { x: 75, y: 50 }, data: {} },
      { id: '__end__', position: { x: 75, y: 600 }, data: {} },
      { id: '__pipeline__build', position: { x: 200, y: 150 }, data: {}, parentId: '__pipeline__' },
      { id: '__task__build.compile', position: { x: 280, y: 220 }, data: {}, parentId: '__pipeline__build' },
    ];
    vi.mocked(applyDagreLayout).mockReturnValue(dagreOutput as any);

    const onGraphChange = vi.fn();
    const { unmount } = render(
      <WorkflowEditor
        pipeline={{
          name: 'bug46',
          pipelines: [{
            name: 'build',
            depends_on: [],
            tasks: [{ name: 'compile', command: 'echo', env: {}, retry: 0, depends_on: [] }],
          }],
        }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('布局')).toBeInTheDocument();
    });

    // 点击布局按钮 → 触发 handleAutoLayout
    const layoutBtn = screen.getByText('布局');
    await userEvent.setup().click(layoutBtn);

    // 通过 onGraphChange 回调捕获布局后的 nodes
    await waitFor(() => {
      expect(onGraphChange).toHaveBeenCalled();
    });

    const lastCall = onGraphChange.mock.calls[onGraphChange.mock.calls.length - 1];
    const changedNodes = lastCall[0] as Array<{ id: string; parentId?: string; position: { x: number; y: number } }>;

    // 找到子节点 __task__build.compile
    const taskNode = changedNodes.find((n) => n.id === '__task__build.compile');
    expect(taskNode, '布局后应包含 task 节点').toBeTruthy();
    expect(taskNode!.parentId, 'task 节点应有 parentId').toBe('__pipeline__build');

    // 关键断言：子节点 position 应为相对父容器的偏移
    // dagre 绝对坐标：{x:280, y:220}；父容器绝对坐标：{x:200, y:150}
    // 转换后应为：{x:80, y:70}（280-200=80, 220-150=70）
    //
    // 修复前：onGraphChange 中的 task 节点 position 为 {x:280, y:220}（绝对坐标当相对用） ❌
    // 修复后：onGraphChange 中的 task 节点 position 为 {x:80, y:70}（正确的相对偏移） ✅
    expect(taskNode!.position.x).toBe(80);
    expect(taskNode!.position.y).toBe(70);

    unmount();
  });
});
