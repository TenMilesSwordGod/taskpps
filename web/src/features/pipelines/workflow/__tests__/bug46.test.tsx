/**
 * Bug #46 回归测试 — 自适应窗口/布局按钮造成子节点位置错乱
 *
 * 复现步骤：在 Pipeline 编辑器中编排混合布局（task + pipeline + subpipeline），
 * 点击工具栏"布局"按钮 → 子节点（有 parentId）的 position 为 dagre 输出的绝对坐标，
 * 但 ReactFlow 将其按相对父容器的偏移解释，导致节点"到处乱飞"。
 *
 * 原根因：handleAutoLayout 调用 applyDagreLayout 后直接将 dagre 的绝对坐标
 * 赋值给所有节点，未将子节点（有 parentId）的 position 转换为相对父容器的偏移。
 *
 * v2 (2026-07): 新布局内核 layoutGraph 自底向上分层计算，子节点坐标天然相对父容器，
 * 不再有"绝对坐标转相对坐标"这一步骤。本回归测试因此改为断言布局结果的
 * 结构性性质（子节点必须落在父容器范围内），不再 mock 已废弃的 applyDagreLayout，
 * 避免把测试绑定到具体像素值上。
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkflowEditor from '../WorkflowEditor';

describe('Bug #46 — 自动布局后子节点 position 应为相对父容器的偏移', () => {
  it('布局后子节点（有 parentId）的相对 position 必须落在父容器范围内', async () => {
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
    const changedNodes = lastCall[0] as Array<{
      id: string;
      parentId?: string;
      position: { x: number; y: number };
      style?: { width?: number; height?: number };
    }>;

    const taskNode = changedNodes.find((n) => n.id === '__task__build.compile');
    const subNode = changedNodes.find((n) => n.id === '__pipeline__build');
    expect(taskNode, '布局后应包含 task 节点').toBeTruthy();
    expect(taskNode!.parentId, 'task 节点应有 parentId').toBe('__pipeline__build');

    // 关键断言：子节点相对坐标必须为有限的非负值，且右/下边界不超出父容器。
    // 修复前（绝对坐标当相对坐标用）task.position 会是 {x:280, y:220} 这类大值，
    // 在父容器尺寸之外 —— 即"到处乱飞"。
    const subW = (subNode?.style?.width as number) ?? 0;
    const subH = (subNode?.style?.height as number) ?? 0;
    expect(Number.isFinite(taskNode!.position.x)).toBe(true);
    expect(Number.isFinite(taskNode!.position.y)).toBe(true);
    expect(taskNode!.position.x).toBeGreaterThanOrEqual(0);
    expect(taskNode!.position.y).toBeGreaterThanOrEqual(0);
    expect(taskNode!.position.x + 180).toBeLessThanOrEqual(subW);
    expect(taskNode!.position.y + 56).toBeLessThanOrEqual(subH);

    unmount();
  });
});
