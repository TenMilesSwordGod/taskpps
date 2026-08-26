import { describe, it, expect } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import { yamlToNodes } from '../yamlToNodes';
import { EDITOR_EDGE_COLOR } from '../edgeStyles';
import type { PipelineDetail } from '@/types';

/**
 * 编辑器外壳测试（n8n 化重设计 v9）
 *
 * 验证画布作用域与边样式接入：
 *   1. 根节点带 wf-editor 作用域类（editor.css 全部规则挂载点，不污染查看模式）
 *   2. yamlToNodes 产生的边使用工厂样式（rail 灰 / start 绿 / implicit 浅灰），
 *      且全部无虚线碎片（n8n 画布无虚线）
 *   3. 哨兵边间距 64px（连线有呼吸空间，不再是短线头）
 */

function makePipeline(): PipelineDetail {
  return {
    name: 'shell-test',
    pipelines: [
      {
        name: 'job',
        depends_on: [],
        // parallel 策略 + 显式 depends_on：确保存在 explicit 边（parallel 无隐式边）
        config: { env: {}, retry: 0, on_failure: '', execution_strategy: 'parallel' },
        tasks: [
          { name: 'a', command: 'echo a', env: {}, retry: 0, depends_on: [] },
          { name: 'b', command: 'echo b', env: {}, retry: 0, depends_on: ['a'] },
        ],
      },
      {
        name: 'seq',
        depends_on: [],
        tasks: [
          { name: 'x', command: 'echo x', env: {}, retry: 0, depends_on: [] },
          { name: 'y', command: 'echo y', env: {}, retry: 0, depends_on: [] },
        ],
      },
    ],
  };
}

describe('编辑器外壳 — 作用域类', () => {
  it('根节点渲染 wf-editor 类（editor.css 作用域挂载点）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor pipeline={makePipeline()} selectedNodeId={null} onNodeSelect={() => {}} />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // wrapper 是 .react-flow 的祖先，带 wf-editor 类
    const wrapper = container.querySelector('.wf-editor');
    expect(wrapper).not.toBeNull();
    expect(wrapper!.querySelector('.react-flow')).not.toBeNull();

    unmount();
  });
});

describe('编辑器外壳 — 边样式接入工厂', () => {
  it('显式边使用主流轨灰，隐式边使用浅灰且无虚线', () => {
    const { edges } = yamlToNodes(makePipeline());

    const explicit = edges.find((e) => e.data?.edgeType === 'explicit');
    expect(explicit?.style?.stroke).toBe(EDITOR_EDGE_COLOR.rail);

    const implicit = edges.find((e) => e.data?.edgeType === 'implicit');
    expect(implicit?.style?.stroke).toBe(EDITOR_EDGE_COLOR.implicit);
    expect(implicit?.style?.strokeDasharray).toBeUndefined();
  });

  it('哨兵边：START 绿 / 下行灰，全部无虚线', () => {
    const { edges } = yamlToNodes(makePipeline());

    const startEdge = edges.find((e) => e.id === '__edge__start_to_pipeline');
    expect(startEdge?.style?.stroke).toBe(EDITOR_EDGE_COLOR.start);

    const endEdge = edges.find((e) => e.id === '__edge__pipeline_to_end');
    expect(endEdge?.style?.stroke).toBe(EDITOR_EDGE_COLOR.rail);

    edges.forEach((e) => {
      expect(e.style?.strokeDasharray).toBeUndefined();
    });
  });

  it('哨兵节点与容器间距 72px（LR 流向，连线呼吸空间）', () => {
    const { nodes } = yamlToNodes(makePipeline());

    const start = nodes.find((n) => n.id === '__start__')!;
    const end = nodes.find((n) => n.id === '__end__')!;
    const root = nodes.find((n) => n.id === '__pipeline__')!;
    const rootH = (root.style as { height?: number }).height ?? 0;
    const rootW = (root.style as { width?: number }).width ?? 0;

    // v11 (LR): START 右缘到容器左缘 = 72（x = -(112 + 72) = -184）
    expect(start.position.x).toBe(-184);
    // START 垂直居中对齐根容器
    expect(start.position.y).toBe(rootH / 2 - 28);
    // END 左缘到容器右缘 = 72
    expect(end.position.x).toBe(rootW + 72);
    expect(end.position.y).toBe(rootH / 2 - 28);
  });
});
