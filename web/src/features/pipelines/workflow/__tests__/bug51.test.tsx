import { describe, it, expect } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import { INK } from '@/features/pipelines/nodes/nodeTokens';
import type { PipelineDetail } from '@/types';

/**
 * Bug #51 RED 测试：编辑模式缺少查看模式的点状背景布局
 *
 * 预期行为：编辑模式的画布背景（容器底色 + 点状图案参数）应与查看模式
 * （PipelineGraph.tsx）保持一致，确保两种模式间切换时视觉连贯。
 *
 * 查看模式配置：
 *   - 容器底色: INK.canvas = #F8FAFC
 *   - 点状背景: variant=Dots, gap=18, size=1, color="#CBD5E1"
 *
 * RED 阶段：以上断言在修复前因不一致必然失败。
 */

function factory(): PipelineDetail {
  return {
    name: 'bg-test',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [{ name: 't1', command: 'echo 1', env: {}, retry: 0, depends_on: [] }],
      },
    ],
  };
}

describe('Bug#51 — 编辑模式背景与查看模式一致', () => {
  it('RED: 容器底色应为 INK.canvas（rgb(248, 250, 252)）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={factory()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={() => {}}
      />,
    );

    // 等 ReactFlow 渲染完成
    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 最外层 div 的 inline backgroundColor
    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper).not.toBeNull();
    // 修复前为 #f5f5f5（rgb(245, 245, 245)），非 INK.canvas（rgb(248, 250, 252)）
    expect(wrapper.style.backgroundColor).toBe('rgb(248, 250, 252)');

    unmount();
  });

  it('RED: 点状 Background gap 应与查看模式一致（gap=18）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={factory()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // Background 组件渲染 SVG <pattern> 元素，gap → pattern width/height
    const pattern = container.querySelector('pattern');
    expect(pattern).not.toBeNull();
    // 修复前 gap=20 → width/height='20'，查看模式 gap=18 → width/height='18'
    expect(pattern!.getAttribute('width')).toBe('18');
    expect(pattern!.getAttribute('height')).toBe('18');

    unmount();
  });

  it('RED: 点状颜色应与查看模式一致（color=#CBD5E1）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={factory()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // @xyflow/react Background 用 CSS 自定义属性传递颜色
    // （见 node_modules 源码：style={{ '--xy-background-pattern-color-props': color }}）
    const bg = container.querySelector('[data-testid="rf__background"]');
    expect(bg).not.toBeNull();
    // 修复前 color='#e5e5e5'，查看模式 color='#CBD5E1'
    expect(bg!.getAttribute('style')).toContain('#CBD5E1');

    unmount();
  });
});
