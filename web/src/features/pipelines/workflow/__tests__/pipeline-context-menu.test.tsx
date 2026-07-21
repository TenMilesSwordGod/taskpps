import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * 验证 Pipeline 根容器右键菜单包含"添加 SubPipeline"项。
 *
 * v7 (2026-07): 用户反馈 Pipeline 上右键没有"添加 SubPipeline"，只有画布空白上有。
 * 修复：contextMenuItems 增加 editorPipeline 分支 + handleAddNodeFromContext 设置 parentId='__pipeline__'。
 */

function makePipeline(): PipelineDetail {
  return {
    name: 'test-pipeline',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [
          { name: 'compile', command: 'echo 1', env: {}, retry: 0, depends_on: [] },
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

describe('Pipeline 节点右键菜单', () => {
  it('右键 Pipeline 节点应含"添加 SubPipeline"', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const pipelineNode = container.querySelector('[data-id="__pipeline__"]');
    expect(pipelineNode, 'Pipeline 节点应存在').not.toBeNull();

    // 右键 Pipeline 节点（模拟 fireEvent 以触发 React 合成事件）
    fireEvent.contextMenu(pipelineNode!, { clientX: 100, clientY: 100 });

    await waitFor(() => {
      const item = findMenuItem(container, '添加 SubPipeline');
      expect(item, '右键菜单应包含"添加 SubPipeline"').not.toBeNull();
    });

    unmount();
  });
});
