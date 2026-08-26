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
 *   - 容器底色: INK.canvas = #FAFAFA（v3 全站外观改造：由 #F8FAFC 暖化）
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
  it('RED: 容器底色应为 INK.canvas（rgb(250, 250, 250)）', async () => {
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
    // v11 (2026-08): INK.canvas 迁移到 n8n 画布底 #F6F8FA —— 断言引用 token 换算的 rgb 值，
    // 防止未来换肤再次误报（rgb(246, 248, 250) = #F6F8FA）
    expect(wrapper.style.backgroundColor).toBe('rgb(246, 248, 250)');

    unmount();
  });

  it('RED: 点状 Background gap 应与查看模式一致（gap=20）', async () => {
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
    // v11: 两画布统一 n8n 点阵 gap=20 → width/height='20'
    expect(pattern!.getAttribute('width')).toBe('20');
    expect(pattern!.getAttribute('height')).toBe('20');

    unmount();
  });

  it('RED: 点状颜色应与查看模式一致（color=#D3DAE4）', async () => {
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
    // v11: n8n 点色 #D3DAE4（查看/编辑两画布一致）
    expect(bg!.getAttribute('style')).toContain('#D3DAE4');

    unmount();
  });
});
