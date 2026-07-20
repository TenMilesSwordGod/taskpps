import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * Bug #41 RED 测试（红测试，确定性失败）
 *
 * 验证：在 SubPipeline 节点上右键 → 点击"添加 Task" →
 * 新增的 Task 节点应进入该 SubPipeline 容器（parentId === 该 SubPipeline 的 id，
 * 且 position 为相对父容器的坐标）。
 *
 * 当前实现（bug）：handleAddNodeFromContext 硬编码 parentContext='canvas-root'，
 * 新增 Task 的 parentId 为空、position 恒为 {x:200,y:200}，不进入 SubPipeline。
 *
 * 测试策略：通过真实右键菜单交互驱动（与 contextMenu.test.tsx 一致），
 * 用 onGraphChange 回传的 nodes 断言新增 Task 节点的 parentId。
 */

function makeSubPipelineData(): PipelineDetail {
  return {
    name: 'bug41-ctx',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [{ name: 't1', command: 'echo 1', env: {}, retry: 0, depends_on: [] }],
      },
    ],
  };
}

const SUB_PIPELINE_ID = '__pipeline__build';

function findMenuItem(container: HTMLElement, text: string): HTMLElement | null {
  const fixedContainers = container.querySelectorAll('div[style*="position: fixed"]');
  for (const fixedDiv of fixedContainers) {
    if (fixedDiv.getAttribute('style')?.includes('width: 0') ||
        fixedDiv.getAttribute('style')?.includes('height: 0')) continue;
    for (const child of fixedDiv.children) {
      if (child instanceof HTMLElement && child.textContent?.trim() === text) {
        return child;
      }
    }
  }
  return null;
}

describe('Bug #41 — 右键 SubPipeline 添加 Task 应进入容器', () => {
  it('右击 SubPipeline 节点 → 菜单点击"添加 Task" → 新 Task 节点 parentId 应为该 SubPipeline', async () => {
    const onGraphChange = vi.fn();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSubPipelineData()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 1. 右击 SubPipeline 节点，弹出其专属右键菜单
    const subNode = container.querySelector(`[data-id*="${SUB_PIPELINE_ID}"]`);
    expect(subNode).not.toBeNull();
    fireEvent.contextMenu(subNode!, { clientX: 350, clientY: 250 });

    // 2. 等待菜单出现并定位"添加 Task"项（来自 SubPipeline 分支）
    let addTaskItem: HTMLElement | null = null;
    await waitFor(() => {
      addTaskItem = findMenuItem(container, '添加 Task');
      expect(addTaskItem).not.toBeNull();
    });

    // 3. 点击"添加 Task"，触发 handleAddNodeFromContext('task')
    fireEvent.click(addTaskItem!);

    // 4. 断言：onGraphChange 回传的新图中，存在新增的 editorTask 节点，
    //    且其 parentId 等于被右键的 SubPipeline 的 id。
    await waitFor(() => {
      expect(onGraphChange).toHaveBeenCalled();
    });

    const lastCall = onGraphChange.mock.calls[onGraphChange.mock.calls.length - 1];
    const changedNodes = lastCall[0] as Array<{ id: string; type?: string; parentId?: string }>;
    const newTask = changedNodes.find(
      (n) => n.id.startsWith('__new__') && n.type === 'editorTask',
    );

    expect(newTask, '应能找到右键新增的 Task 节点').toBeTruthy();
    // 关键断言：新增 Task 应进入被右键的 SubPipeline 容器
    expect(newTask?.parentId).toBe(SUB_PIPELINE_ID);

    unmount();
  });

  it('右击 SubPipeline 节点 → 新 Task 节点 position 应为相对父容器的坐标（非固定 200,200）', async () => {
    const onGraphChange = vi.fn();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSubPipelineData()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const subNode = container.querySelector(`[data-id*="${SUB_PIPELINE_ID}"]`);
    fireEvent.contextMenu(subNode!, { clientX: 350, clientY: 250 });

    let addTaskItem: HTMLElement | null = null;
    await waitFor(() => {
      addTaskItem = findMenuItem(container, '添加 Task');
      expect(addTaskItem).not.toBeNull();
    });

    fireEvent.click(addTaskItem!);

    await waitFor(() => {
      expect(onGraphChange).toHaveBeenCalled();
    });

    const lastCall = onGraphChange.mock.calls[onGraphChange.mock.calls.length - 1];
    const changedNodes = lastCall[0] as Array<{ id: string; type?: string; position?: { x: number; y: number } }>;
    const newTask = changedNodes.find(
      (n) => n.id.startsWith('__new__') && n.type === 'editorTask',
    );

    expect(newTask, '应能找到右键新增的 Task 节点').toBeTruthy();
    // 关键断言：相对父容器的坐标不应是硬编码的画布根级 (200,200)
    expect(newTask?.position).not.toEqual({ x: 200, y: 200 });

    unmount();
  });
});
