import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import { renderWithProvider } from './test-utils';
import EditorSubPipelineNode from '../nodes/EditorSubPipelineNode';
import type { PipelineDetail } from '@/types';

/**
 * 折叠/展开交互测试 —— v7 (2026-08) 重写
 *
 * v7 视觉统一决策：SubPipeline 容器与查看模式 SubpipelineGroupNode 对齐后
 * 移除折叠功能（查看模式无此概念，双模式一致性优先）。
 * data.collapsed 字段保留兼容历史数据，但组件不再渲染折叠 UI、
 * 右键菜单不再提供折叠/展开项。
 *
 * 本文件现在验证的契约：
 *   1. 右键菜单不再出现"折叠/展开"项
 *   2. 容器组件任何状态下都渲染端口（无折叠态分支）
 *   3. 不再渲染 collapse-toggle 按钮
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

describe('折叠功能移除（v7 视觉统一）', () => {
  it('右键 SubPipeline 容器 → 菜单不再包含"折叠/展开"项', async () => {
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
      // 菜单已弹出（有"属性"项）
      expect(findMenuItem(container, '属性')).not.toBeNull();
    });

    expect(findMenuItem(container, '折叠')).toBeNull();
    expect(findMenuItem(container, '展开')).toBeNull();

    unmount();
  });

  it('容器组件始终渲染端口（无折叠态分支）', () => {
    // data.collapsed=true 是历史遗留数据，组件应忽略它照常渲染端口
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode
        data={{ label: 'build', executionStrategy: 'sequential', collapsed: true }}
      />,
    );
    const handles = container.querySelectorAll('.react-flow__handle');
    expect(handles.length).toBe(3); // in/out/post
    unmount();
  });

  it('不再渲染 collapse-toggle 按钮', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    expect(container.querySelector('.collapse-toggle')).toBeNull();
    unmount();
  });

  it('header 行始终显示组名与策略徽章（替代旧折叠摘要）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode
        data={{ label: 'build', executionStrategy: 'parallel', childrenCount: 2 }}
      />,
    );
    expect(container.textContent).toContain('build');
    expect(container.textContent).toContain('PAR');
    expect(container.textContent).toContain('2 tasks');
    unmount();
  });
});
