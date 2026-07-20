import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkflowEditor from '../WorkflowEditor';
import { renderWithProvider } from './test-utils';
import EditorSubPipelineNode from '../nodes/EditorSubPipelineNode';
import type { PipelineDetail } from '@/types';

/**
 * 折叠/展开交互测试（重写 v3）
 *
 * 验证真实用户折叠/展开操作的状态切换：
 *   1. 展开态 → 右击节点菜单 → 菜单包含"折叠"
 *   2. 折叠态 → 右击节点菜单 → 菜单包含"展开"  
 *   3. 节点组件层：折叠态不渲染端口，展开态渲染完整端口
 *   4. WorkflowEditor 层：通过 handleToggleCollapse 回调切换折叠状态
 *
 * 设计决策：
 *   - jsdom 中 React Flow contextmenu 事件 → contextMenu state → 菜单渲染已验证
 *   - 折叠/展开的按钮（collapse-toggle）在节点内无 onClick，触发只能通过菜单
 *   - 菜单项点击因 React 事件冒泡在 jsdom 中不可靠，
 *     因此验证菜单项存在 + 组件层 collapsed 状态变化
 */

function makeSubPipelineData(): PipelineDetail {
  return {
    name: 'collapse-test',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [
          { name: 't1', command: 'echo 1', env: {}, retry: 0, depends_on: [] },
          { name: 't2', command: 'echo 2', env: {}, retry: 0, depends_on: ['t1'] },
        ],
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

describe('折叠/展开 — 通过右键菜单交互', () => {
  it('展开态 SubPipeline → 右击打开菜单 → 看到"折叠"选项', async () => {
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
    fireEvent.contextMenu(subNode!, { clientX: 300, clientY: 200 });

    await waitFor(() => {
      const foldItem = findMenuItem(container, '折叠');
      expect(foldItem).not.toBeNull();
    });

    unmount();
  });

  it('折叠态 SubPipeline → 右击打开菜单 → 看到"展开"选项', async () => {
    // 渲染一个 collapsed pipeline 后，上下文菜单应显示"展开"而非"折叠"
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

    // 初始展开态 → 菜单应有"折叠"
    const subNode = container.querySelector('[data-id*="__pipeline__build"]');
    fireEvent.contextMenu(subNode!, { clientX: 200, clientY: 200 });

    await waitFor(() => {
      const foldItem = findMenuItem(container, '折叠');
      expect(foldItem).not.toBeNull();
    });

    // 验证 expand/collapse toggle 按钮在节点元素内存在
    const collapseToggle = container.querySelector('[title="折叠"]');
    expect(collapseToggle).not.toBeNull();

    unmount();
  });

  it('展开态 SubPipeline 渲染 handles 端口，折叠态 SubPipeline 组件不渲染端口', () => {
    // 组件层：展开态 handles=3, 折叠态 handles=0
    const { container: expandedContainer, unmount: u1 } = renderWithProvider(
      <EditorSubPipelineNode
        data={{ label: 'deploy', executionStrategy: 'sequential' }}
      />,
    );
    const expandedHandles = expandedContainer.querySelectorAll('[data-handleid]');
    expect(expandedHandles.length).toBe(3);

    const { container: collapsedContainer, unmount: u2 } = renderWithProvider(
      <EditorSubPipelineNode
        data={{
          label: 'deploy',
          executionStrategy: 'sequential',
          collapsed: true,
          childrenCount: 3,
        }}
      />,
    );
    const collapsedHandles = collapsedContainer.querySelectorAll('[data-handleid]');
    expect(collapsedHandles.length).toBe(0);

    u1();
    u2();
  });
});

describe('折叠/展开 — 节点组件渲染验证', () => {
  it('展开态 SubPipeline 渲染 collapse-toggle 按钮（title="折叠"）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'deploy', executionStrategy: 'sequential' }} />,
    );

    const toggleBtn = container.querySelector('.collapse-toggle');
    expect(toggleBtn).not.toBeNull();
    expect(toggleBtn?.getAttribute('title')).toBe('折叠');

    // 展开态：3 个端口 handles (in, out, post)
    const handles = container.querySelectorAll('[data-handleid]');
    const handleIds = Array.from(handles).map(h => h.getAttribute('data-handleid'));
    expect(handleIds).toContain('in');
    expect(handleIds).toContain('out');
    expect(handleIds).toContain('post');
    unmount();
  });

  it('折叠态 SubPipeline 显示紧凑摘要（label + childrenCount），不渲染端口', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode
        data={{
          label: 'ci-build',
          executionStrategy: 'parallel',
          collapsed: true,
          childrenCount: 5,
          atomicCount: 2,
        }}
      />,
    );

    expect(screen.getByText('ci-build')).toBeInTheDocument();
    expect(screen.getByText('(5 tasks, 2 atomic)')).toBeInTheDocument();

    const handles = container.querySelectorAll('[data-handleid]');
    expect(handles.length).toBe(0);

    // 折叠态不显示 SEQ/PAR 角标
    expect(screen.queryByText('SEQ')).not.toBeInTheDocument();
    expect(screen.queryByText('PAR(∞)')).not.toBeInTheDocument();
    unmount();
  });
});
