import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * Bug #43 RED 测试：有 SubPipeline 的数据中 Task 节点右键菜单不弹出、属性面板为空
 *
 * 期望：无论 pipeline 数据是否有 SubPipeline，右键点击 Task 节点都应弹出菜单
 * （含"属性"/"删除"），且 onNodeSelect 应被正确调用以展示 PropertyPanel。
 *
 * 当前场景：数据含 SubPipeline（含内嵌 Task）。右键该 Task 节点。
 *
 * 前序修复（#35/#39/#40/#41）可能已隐式解决此问题。
 * 若测试通过（隐式修复），confidence 记为 'fixed_already'。
 */

function makePipelineWithSubPipelineAndTask(): PipelineDetail {
  return {
    name: 'bug43-pipeline',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [
          { name: 'compile', command: 'gcc main.c', env: {}, retry: 0, depends_on: [] },
          { name: 'test', command: 'make test', env: {}, retry: 0, depends_on: ['compile'] },
        ],
      },
    ],
  };
}

/** Task 节点在 SubPipeline 内的 id */
const TASK_NODE_ID = '__task__build.compile';

/** 查找自定义 div 右键菜单中指定文本的项 */
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

describe('Bug #43 — SubPipeline 存在时 Task 节点右键菜单', () => {
  it('右击 SubPipeline 内的 Task 节点 → 右键菜单弹出（含"属性"和"删除"）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makePipelineWithSubPipelineAndTask()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 找到 SubPipeline 内嵌的 Task 节点（data-id 含 __task__）
    const taskNode = container.querySelector(`[data-id="${TASK_NODE_ID}"]`);
    expect(taskNode, 'Task 节点应在 DOM 中').not.toBeNull();

    // 右键该 Task 节点
    fireEvent.contextMenu(taskNode!, { clientX: 350, clientY: 250 });

    // 断言：菜单中出现"属性"和"删除"（表明菜单弹出）
    await waitFor(() => {
      const propertiesItem = findMenuItem(container, '属性');
      const deleteItem = findMenuItem(container, '删除');
      expect(propertiesItem, '右键菜单应包含"属性"').not.toBeNull();
      expect(deleteItem, '右键菜单应包含"删除"').not.toBeNull();
    });

    unmount();
  });

  it('右键 Task 节点 → 点击"属性" → onNodeSelect 被调用且传入正确 nodeId', async () => {
    const onNodeSelect = vi.fn();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makePipelineWithSubPipelineAndTask()}
        selectedNodeId={null}
        onNodeSelect={onNodeSelect}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const taskNode = container.querySelector(`[data-id="${TASK_NODE_ID}"]`);
    expect(taskNode).not.toBeNull();
    fireEvent.contextMenu(taskNode!, { clientX: 350, clientY: 250 });

    let propertiesItem: HTMLElement | null = null;
    await waitFor(() => {
      propertiesItem = findMenuItem(container, '属性');
      expect(propertiesItem).not.toBeNull();
    });

    // 点击"属性"
    fireEvent.click(propertiesItem!);

    await waitFor(() => {
      expect(onNodeSelect).toHaveBeenCalledWith(TASK_NODE_ID);
    });

    unmount();
  });

  it('右键 Task 节点 → 菜单也包含"折叠"（因 Task 是容器类型）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makePipelineWithSubPipelineAndTask()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const taskNode = container.querySelector(`[data-id="${TASK_NODE_ID}"]`);
    expect(taskNode).not.toBeNull();
    fireEvent.contextMenu(taskNode!, { clientX: 350, clientY: 250 });

    await waitFor(() => {
      // 注意(2026-07): 当前 isContainer 包括 editorTask，所以 Task 节点会显示"折叠"
      // 即使"折叠"对 Task 不实用，仍作为上下文的一部分验证
      const foldItem = findMenuItem(container, '折叠');
      expect(foldItem, '菜单应包含"折叠"（isContainer 包括 editorTask）').not.toBeNull();
    });

    unmount();
  });

  it('SubPipeline 数据中右键 Task 节点 → 菜单项不多于 1 份（无双重渲染）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makePipelineWithSubPipelineAndTask()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const taskNode = container.querySelector(`[data-id="${TASK_NODE_ID}"]`);
    expect(taskNode).not.toBeNull();
    fireEvent.contextMenu(taskNode!, { clientX: 350, clientY: 250 });

    await waitFor(() => {
      // 确认无 antd Dropdown（#40 已修复）
      expect(document.querySelector('.ant-dropdown')).toBeNull();
    });

    // 计数"属性"菜单项出现次数（应为 1）
    await waitFor(() => {
      // 通过自定义 div 查找匹配项
      const fixedMenus = container.querySelectorAll('div[style*="position: fixed"]');
      let propertiesCount = 0;
      for (const menu of fixedMenus) {
        for (const child of menu.children) {
          if (child instanceof HTMLElement && child.textContent?.trim() === '属性') {
            propertiesCount++;
          }
        }
      }
      // 双重渲染会出现 2 次，正常应为 1 次
      expect(propertiesCount).toBeLessThanOrEqual(1);
    });

    unmount();
  });
});
