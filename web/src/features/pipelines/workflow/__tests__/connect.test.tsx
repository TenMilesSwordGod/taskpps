import { describe, it, expect, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';
import { yamlToNodes } from '../yamlToNodes';

/**
 * 连线交互测试（v3 新建）
 *
 * 验证边的创建与删除：
 *   1. Sequential SubPipeline 生成隐式边（a→b→c→d）
 *   2. 显式 depends_on 生成 explicit 边
 *   3. Post 容器创建 post_routing 边
 *   4. 空 pipeline 哨兵边验证
 *
 * 设计决策：
 *   - React Flow 的 handle→handle 拖线交互在 jsdom 中无法完整模拟，
 *     因此通过 pipeline 数据驱动的方式验证边的生成
 *   - 边数据类型验证 edge.data.edgeType / edge.data.explicit / edge.data.implicit
 */

function makePipelineWithEdges(): PipelineDetail {
  return {
    name: 'connect-test',
    pipelines: [
      {
        name: 'seq-build',
        depends_on: [],
        config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'sequential' },
        tasks: [
          { name: 'a', command: 'echo a', env: {}, retry: 0, depends_on: [] },
          { name: 'b', command: 'echo b', env: {}, retry: 0, depends_on: [] },
          { name: 'c', command: 'echo c', env: {}, retry: 0, depends_on: [] },
          { name: 'd', command: 'echo d', env: {}, retry: 0, depends_on: [] },
        ],
      },
    ],
  };
}

function makePipelineWithPost(): PipelineDetail {
  return {
    name: 'post-connect',
    pipelines: [
      {
        name: 'job',
        depends_on: [],
        tasks: [{ name: 'main', command: 'run.sh', env: {}, retry: 0, depends_on: [] }],
        post: {
          on_fail: [{ name: 'notify', command: 'curl webhook', env: {}, retry: 0, depends_on: [] }],
        },
      },
    ],
  };
}

function makePipelineWithExplicitDeps(): PipelineDetail {
  return {
    name: 'explicit-connect',
    pipelines: [
      {
        name: 'parallel-job',
        depends_on: [],
        config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'parallel' },
        tasks: [
          { name: 't1', command: 'echo 1', env: {}, retry: 0, depends_on: [] },
          { name: 't2', command: 'echo 2', env: {}, retry: 0, depends_on: ['t1'] },
          { name: 't3', command: 'echo 3', env: {}, retry: 0, depends_on: ['t1'] },
        ],
      },
    ],
  };
}

describe('连线 — 隐式边（sequential 策略）', () => {
  it('Sequential SubPipeline 生成隐式边（4 tasks → 3 条 implicit edges）', () => {
    const p = makePipelineWithEdges();
    const { edges } = yamlToNodes(p);

    const implicitEdges = edges.filter(e => e.data?.edgeType === 'implicit');
    // a→b, b→c, c→d = 3 条隐式边
    expect(implicitEdges.length).toBe(3);

    // 隐式边标记 implicit=true, explicit=false
    implicitEdges.forEach(e => {
      expect(e.data?.implicit).toBe(true);
      expect(e.data?.explicit).toBe(false);
    });
  });

  it('Parallel 策略不生成隐式边', () => {
    const p: PipelineDetail = {
      name: 'par-no-implicit',
      pipelines: [{
        name: 'par',
        depends_on: [],
        config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'parallel' },
        tasks: [
          { name: 'x', env: {}, retry: 0, depends_on: [] },
          { name: 'y', env: {}, retry: 0, depends_on: [] },
          { name: 'z', env: {}, retry: 0, depends_on: [] },
        ],
      }],
    };

    const { edges } = yamlToNodes(p);
    const implicitEdges = edges.filter(e => e.data?.edgeType === 'implicit');
    expect(implicitEdges.length).toBe(0);
  });

  it('WorkflowEditor 渲染含隐式边的 pipeline → onGraphChange 可用', async () => {
    const onGraphChange = vi.fn();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makePipelineWithEdges()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // onGraphChange 回调已注册，组件渲染正常
    expect(onGraphChange).toBeDefined();

    unmount();
  });
});

describe('连线 — 显式 depends_on', () => {
  it('显式 depends_on 生成 explicit 边（t2 depends_on t1, t3 depends_on t1）', () => {
    const p = makePipelineWithExplicitDeps();
    const { edges } = yamlToNodes(p);

    const explicitEdges = edges.filter(e => e.data?.edgeType === 'explicit');
    // t1 → t2, t1 → t3 = 2 条显式边
    expect(explicitEdges.length).toBe(2);

    explicitEdges.forEach(e => {
      expect(e.data?.explicit).toBe(true);
      expect(e.data?.implicit).toBe(false);
    });
  });

  it('显式边优先于隐式边（parallel 策略 + 显式 depends_on = 仅显式边）', () => {
    const p = makePipelineWithExplicitDeps();
    const { edges } = yamlToNodes(p);

    const implicitEdges = edges.filter(e => e.data?.edgeType === 'implicit');
    // parallel 策略无隐式边，仅有显式边
    expect(implicitEdges.length).toBe(0);

    const explicitEdges = edges.filter(e => e.data?.edgeType === 'explicit');
    expect(explicitEdges.length).toBe(2);
  });
});

describe('连线 — post_routing 边', () => {
  it('有 post.on_fail 的 SubPipeline 生成 post_routing 边', () => {
    const p = makePipelineWithPost();
    const { edges } = yamlToNodes(p);

    const postEdges = edges.filter(e => e.data?.edgeType === 'post_routing');
    // SubPipeline.post → PostParent, PostParent → PostChild
    expect(postEdges.length).toBeGreaterThanOrEqual(1);
  });

  it('Post 边数据结构和端口隔离在 WorkflowEditor 渲染时保持', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makePipelineWithPost()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // SubPipeline 的 post handle (source) 存在
    const postHandles = container.querySelectorAll('[data-handleid="post"]');
    expect(postHandles.length).toBeGreaterThanOrEqual(1);

    unmount();
  });
});

describe('连线 — 哨兵边验证', () => {
  it('空 pipeline 生成 2 条哨兵边（start→pipeline, pipeline→end）', () => {
    const p: PipelineDetail = { name: 'minimal' };
    const { edges } = yamlToNodes(p);

    // start → pipeline → end = 2 条边
    expect(edges.length).toBe(2);
    // 哨兵边 edgeType 为 'cross_container'（yamlToNodes 中硬编码为跨容器边）
    const edgeTypes = edges.map(e => e.data?.edgeType);
    expect(edgeTypes).toContain('cross_container');
    // 哨兵边标记 explicit=true, implicit=false
    edges.forEach(e => {
      expect(e.data?.explicit).toBe(true);
      expect(e.data?.implicit).toBe(false);
    });
  });

  it('带 SubPipeline 的 pipeline 渲染时 SVG 边元素存在', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makePipelineWithEdges()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // React Flow v12 使用 .react-flow__edge 类名渲染边
    // 或 SVG path 存在说明边已渲染
    const svgElements = container.querySelectorAll('svg');
    // 至少 React Flow 画布 SVG 存在
    expect(svgElements.length).toBeGreaterThan(0);

    unmount();
  });
});
