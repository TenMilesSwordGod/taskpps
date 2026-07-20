import { describe, it, expect } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import WorkflowEditor from '../../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * Bug #40 RED 测试：右键上下文菜单双重渲染。
 *
 * 预期行为：右键唤起的上下文菜单只应渲染一份（保留自定义绝对定位 div 菜单），
 * 不应同时存在 antd <Dropdown>（会 portal 到 document.body 生成 .ant-dropdown）
 * 与自定义 div 两套菜单——两者 zIndex 冲突（1000 vs 1001）会造成闪烁/双重菜单项。
 *
 * 当前（bug）表现：WorkflowEditor 内有两段相同条件 `{contextMenu && contextMenu.open && ...}`：
 *   1) antd <Dropdown menu={{ items: contextMenuItems }} open .../>（约 796-816 行）
 *   2) 自定义绝对定位 div 菜单，contextMenuItems.map(...)（约 819-862 行）
 * 二者同时渲染，导致同一菜单项（如"添加 SubPipeline"）在文档中出现两次。
 *
 * 断言：右键画布空白后，菜单项"添加 SubPipeline"在整个文档中只出现 1 次，
 * 且不存在 antd Dropdown 容器（.ant-dropdown）。修复前必然确定性失败（RED）。
 */

function makeSimplePipeline(): PipelineDetail {
  return {
    name: 'ctx-dup',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [{ name: 't1', command: 'echo 1', env: {}, retry: 0, depends_on: [] }],
      },
    ],
  };
}

// 统计整个文档（含 portal 到 document.body 的 antd 菜单）中匹配文本的元素数量
function countByText(text: string): number {
  const all = document.body.querySelectorAll('*');
  let count = 0;
  for (const el of all) {
    // 仅统计"叶子文本节点直接持有该文本"的元素，避免祖先容器被重复计数
    const own = Array.from(el.childNodes)
      .filter((n) => n.nodeType === Node.TEXT_NODE)
      .map((n) => n.textContent?.trim() ?? '')
      .join('');
    if (own === text) count += 1;
  }
  return count;
}

describe('Bug#40 — 右键上下文菜单双重渲染', () => {
  it('右键画布空白后，同一菜单项只应渲染一份（且无 antd Dropdown 容器）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSimplePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 右键画布空白区域（pane）唤起上下文菜单
    const pane = container.querySelector('.react-flow__pane');
    expect(pane).not.toBeNull();
    fireEvent.contextMenu(pane!, { clientX: 300, clientY: 200 });

    // 等待菜单渲染
    await waitFor(() => {
      expect(countByText('添加 SubPipeline')).toBeGreaterThan(0);
    });

    // 不应存在 antd Dropdown 容器（应移除冗余的 antd Dropdown，仅保留自定义 div）
    expect(document.querySelector('.ant-dropdown')).toBeNull();

    // 菜单项"添加 SubPipeline"在文档中只应出现 1 次（双重渲染会出现 2 次）
    expect(countByText('添加 SubPipeline')).toBe(1);

    unmount();
  });
});
