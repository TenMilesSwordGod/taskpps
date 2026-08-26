/**
 * Bug #46 回归测试 — 自动布局后子节点必须落在父容器内（相对偏移 + 边界内）
 *
 * 历史根因：handleAutoLayout 旧实现把【所有节点】（含带 parentId 的嵌套子节点）
 * 一股脑喂给 dagre。dagre 对父子层级一无所知，且 task 与容器间无连线，
 * 于是子节点被散射到画布任意处；再经"绝对 - 父绝对"单层换算得到的相对偏移
 * 往往极大，子节点飞出容器 → 视觉混乱（"点击 dagre 后乱成一团"）。
 *
 * v12 修复：分层自动布局（editorAutoLayout）。仅顶层容器图进 dagre，
 * 嵌套子节点（subpipeline 内 task / Post 容器内 post 子节点）按父容器重新打包，
 * 保证始终落在父容器边界内。
 *
 * 断言策略：
 *   1. 点击"布局"后，所有带 parentId 的节点 position 必须是"相对偏移"
 *      （小数值，而非 dagre 的 canvas 级绝对大值）；
 *   2. 且该相对偏移必须落在父容器 [0,width]×[0,height] 边界内（核心防乱飞）。
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkflowEditor from '../WorkflowEditor';

describe('Bug #46 — 自动布局后子节点必须落在父容器内（不再乱飞）', () => {
  it('布局后嵌套子节点（task / post 子节点）的 position 为相对偏移且落在父容器边界内', async () => {
    const onGraphChange = vi.fn();

    // 构造一个含 2 个依赖 task + post 的 subpipeline，充分触发嵌套层级
    const { unmount } = render(
      <WorkflowEditor
        pipeline={{
          name: 'bug46',
          pipelines: [{
            name: 'build',
            depends_on: [],
            tasks: [
              { name: 'compile', command: 'echo', env: {}, retry: 0, depends_on: [] },
              { name: 'package', command: 'echo', env: {}, retry: 0, depends_on: ['compile'] },
            ],
            post: {
              on_fail: [{ name: 'alert', command: 'echo', env: {}, retry: 0, depends_on: [] }],
            },
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

    await userEvent.setup().click(screen.getByText('布局'));

    await waitFor(() => {
      expect(onGraphChange).toHaveBeenCalled();
    });

    const lastCall = onGraphChange.mock.calls[onGraphChange.mock.calls.length - 1];
    const changedNodes = lastCall[0] as Array<{
      id: string;
      type?: string;
      parentId?: string;
      position: { x: number; y: number };
      style?: { width?: number; height?: number };
      data?: { parentTaskId?: string };
    }>;
    const nodeById = new Map(changedNodes.map((n) => [n.id, n]));

    // 找到父容器尺寸
    const sub = nodeById.get('__pipeline__build');
    const postParent = nodeById.get('__post____pipeline__build_parent');
    expect(sub, '应存在 build subpipeline 容器').toBeTruthy();
    expect(postParent, '应存在 build 的 Post 父容器').toBeTruthy();

    const subW = sub!.style?.width ?? 0;
    const subH = sub!.style?.height ?? 0;
    const postW = postParent!.style?.width ?? 0;
    const postH = postParent!.style?.height ?? 0;

    // 校验所有嵌套子节点：相对偏移 + 落在父容器边界内
    const checkChild = (childId: string, parentW: number, parentH: number) => {
      const child = nodeById.get(childId);
      expect(child, `应存在子节点 ${childId}`).toBeTruthy();
      expect(child!.parentId, `${childId} 应有 parentId`).toBeTruthy();
      const { x, y } = child!.position;
      // 相对偏移必须是小值（非 dagre 的 canvas 级绝对坐标，通常 > 1000）
      expect(Math.abs(x)).toBeLessThan(2000);
      expect(Math.abs(y)).toBeLessThan(2000);
      // 必须落在父容器边界内（核心防乱飞断言）
      expect(x).toBeGreaterThanOrEqual(0);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(parentW);
      expect(y).toBeLessThanOrEqual(parentH);
    };

    checkChild('__task__build.compile', subW, subH);
    checkChild('__task__build.package', subW, subH);
    checkChild('__postchild____post____pipeline__build_parent_on_fail_0', postW, postH);

    unmount();
  });
});
