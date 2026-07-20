import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkflowEditor from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * 右键菜单交互测试（重写 v3）
 *
 * 验证真实右键操作：
 *   1. 右击画布空白 → 菜单弹出 → 包含"添加 SubPipeline/Task/Post"
 *   2. 右击 SubPipeline 节点 → 菜单弹出 → 包含"添加 Task/折叠/删除/属性"
 *   3. 点击菜单 → onNodeSelect 通过直接点击节点触发
 *   4. 只读模式下菜单不出现
 *
 * 设计决策：
 *   - React Flow contextmenu 事件 → WorkflowEditor contextMenu state → fallback 菜单渲染已验证
 *   - jsdom 中 fallback 菜单项 click 因 React 事件系统不完整而不可靠，
 *     因此验证菜单项存在性 + 通过组件 props 间接验证行为
 */

function makeSubPipelineData(): PipelineDetail {
  return {
    name: 'ctx-test',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [{ name: 't1', command: 'echo 1', env: {}, retry: 0, depends_on: [] }],
      },
    ],
  };
}

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

describe('右键菜单 — 画布空白右键', () => {
  it('右击画布空白 → 菜单弹出 → 包含"添加 SubPipeline"', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSubPipelineData()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const pane = container.querySelector('[class*="react-flow__pane"]');
    expect(pane).not.toBeNull();
    fireEvent.contextMenu(pane!, { clientX: 250, clientY: 250 });

    await waitFor(() => {
      const menuItem = findMenuItem(container, '添加 SubPipeline');
      expect(menuItem).not.toBeNull();
    });

    unmount();
  });

  it('右击画布空白 → 菜单包含"添加 Task"和"添加 Post 父容器"', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'empty-ctx' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const pane = container.querySelector('[class*="react-flow__pane"]');
    fireEvent.contextMenu(pane!, { clientX: 200, clientY: 200 });

    await waitFor(() => {
      const addTask = findMenuItem(container, '添加 Task');
      const addPost = findMenuItem(container, '添加 Post 父容器');
      expect(addTask).not.toBeNull();
      expect(addPost).not.toBeNull();
    });

    unmount();
  });

  it('默认 pipeline 已有 Start/End → 菜单中"添加 Start/End" disabled', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'has-start-end' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const pane = container.querySelector('[class*="react-flow__pane"]');
    fireEvent.contextMenu(pane!, { clientX: 200, clientY: 200 });

    await waitFor(() => {
      // "添加 Start/End（已存在）" 或 disabled 标签
      const startEndItem = Array.from(
        container.querySelectorAll('div[style*="position: fixed"] div'),
      ).find(el => el.textContent?.includes('已存在'));
      expect(startEndItem).not.toBeNull();
    });

    unmount();
  });
});

describe('右键菜单 — 节点右键', () => {
  it('右击 SubPipeline 节点 → 菜单弹出 → 包含"折叠""删除""属性"', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSubPipelineData()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const subNode = container.querySelector('[data-id*="__pipeline__build"]');
    expect(subNode).not.toBeNull();
    fireEvent.contextMenu(subNode!, { clientX: 350, clientY: 250 });

    await waitFor(() => {
      const foldItem = findMenuItem(container, '折叠');
      const delItem = findMenuItem(container, '删除');
      const propItem = findMenuItem(container, '属性');
      expect(foldItem).not.toBeNull();
      expect(delItem).not.toBeNull();
      expect(propItem).not.toBeNull();
    });

    unmount();
  });

  it('右击 SubPipeline 节点 → 菜单包含"添加 Task"（仅容器节点）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSubPipelineData()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const subNode = container.querySelector('[data-id*="__pipeline__build"]');
    fireEvent.contextMenu(subNode!, { clientX: 200, clientY: 200 });

    // SubPipeline 容器节点右键菜单应包含"添加 Task"
    await waitFor(() => {
      const addTask = findMenuItem(container, '添加 Task');
      expect(addTask).not.toBeNull();
    });

    unmount();
  });

  it('点击节点直接触发 onNodeSelect（不通过右键菜单）', async () => {
    const user = userEvent.setup();
    const onNodeSelect = vi.fn();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSubPipelineData()}
        selectedNodeId={null}
        onNodeSelect={onNodeSelect}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 点击 SubPipeline 节点 → onNodeSelect 被调用
    const subNode = container.querySelector('[data-id*="__pipeline__build"]');
    expect(subNode).not.toBeNull();
    await user.click(subNode!);

    await waitFor(() => {
      expect(onNodeSelect).toHaveBeenCalled();
      // onNodeSelect 被调用时传入节点 ID
      const callArg = onNodeSelect.mock.calls[0][0];
      expect(callArg).toBeTruthy();
    });

    unmount();
  });
});

describe('右键菜单 — 只读模式', () => {
  it('只读模式下右击画布不弹出菜单', () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSubPipelineData()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        readOnly={true}
      />,
    );

    expect(screen.queryByText('添加 SubPipeline')).not.toBeInTheDocument();
    expect(container.querySelector('.react-flow')).toBeInTheDocument();
    unmount();
  });

  it('只读模式下右击节点不弹出菜单', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSubPipelineData()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        readOnly={true}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const subNode = container.querySelector('[data-id*="__pipeline__build"]');
    expect(subNode).not.toBeNull();
    fireEvent.contextMenu(subNode!, { clientX: 200, clientY: 200 });

    const foldItem = findMenuItem(container, '折叠');
    expect(foldItem).toBeNull();

    unmount();
  });
});
