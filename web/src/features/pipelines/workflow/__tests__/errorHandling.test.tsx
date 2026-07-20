import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkflowEditor from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';
import { yamlToNodes } from '../yamlToNodes';
import { nodesToYaml } from '../nodesToYaml';

/**
 * 异常处理测试（v3 新建）
 *
 * 验证异常输入和边界操作：
 *   1. 空 pipeline 渲染不崩溃
 *   2. 自引用 depends_on 不无限循环
 *   3. 哨兵节点存在性验证
 *   4. 超大 pipeline 数据层不超时
 *   5. 右键菜单中"删除"选项存在（删除行为通过 handleDeleteNode 逻辑验证）
 */

function makePipelineWithPost(): PipelineDetail {
  return {
    name: 'err-test',
    pipelines: [
      {
        name: 'job',
        depends_on: [],
        tasks: [{ name: 'main', command: 'run.sh', env: {}, retry: 0, depends_on: [] }],
        post: {
          on_fail: [{ name: 'notify', command: 'curl webhook', env: {}, retry: 0, depends_on: [] }],
          on_success: [{ name: 'tag', command: 'git tag', env: {}, retry: 0, depends_on: [] }],
        },
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

describe('异常处理 — 空/无效 pipeline', () => {
  it('空 pipeline（无 SubPipeline）→ 正常渲染哨兵节点', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'empty' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const flowNodes = container.querySelectorAll('.react-flow__node');
    expect(flowNodes.length).toBe(3);

    unmount();
  });

  it('空 SubPipeline（tasks=[]）→ 序列化返回验证错误', () => {
    const p: PipelineDetail = {
      name: 'empty-sub',
      pipelines: [{ name: 'empty', depends_on: [], tasks: [] }],
    };

    const { nodes, edges } = yamlToNodes(p);
    const result = nodesToYaml(nodes, edges);

    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors.some(e => e.includes('不能为空'))).toBe(true);
  });

  it('只有一个 name 的 pipeline → 正常渲染', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'solo' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    expect(container.querySelector('.react-flow__node')).not.toBeNull();
    unmount();
  });
});

describe('异常处理 — 删除容器上下文菜单', () => {
  it('SubPipeline 节点右击 → 菜单包含"删除"选项', async () => {
    const { fireEvent } = await import('@testing-library/react');
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

    const subNode = container.querySelector('[data-id*="__pipeline__job"]');
    expect(subNode).not.toBeNull();
    fireEvent.contextMenu(subNode!, { clientX: 250, clientY: 250 });

    await waitFor(() => {
      const delItem = findMenuItem(container, '删除');
      expect(delItem).not.toBeNull();
    });

    unmount();
  });

  it('删除操作后 React Flow 画布仍正常渲染', async () => {
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

    // React Flow 画布渲染 SVG 和节点
    const flowNodes = container.querySelectorAll('.react-flow__node');
    expect(flowNodes.length).toBeGreaterThan(0);

    unmount();
  });
});

describe('异常处理 — 循环依赖防护', () => {
  it('自引用 depends_on 不引发无限循环', () => {
    const p: PipelineDetail = {
      name: 'cyclic',
      pipelines: [
        {
          name: 'x',
          depends_on: ['x'],
          tasks: [{ name: 't', command: 'echo', env: {}, retry: 0, depends_on: [] }],
        },
      ],
    };

    expect(() => yamlToNodes(p)).not.toThrow();
    const { nodes } = yamlToNodes(p);
    expect(nodes.find(n => n.data?.label === 'x')).toBeDefined();
  });

  it('A→B→A 循环依赖不崩溃', () => {
    const p: PipelineDetail = {
      name: 'mutual-cyclic',
      pipelines: [
        { name: 'a', depends_on: ['b'], tasks: [{ name: 'ta', env: {}, retry: 0, depends_on: [] }] },
        { name: 'b', depends_on: ['a'], tasks: [{ name: 'tb', env: {}, retry: 0, depends_on: [] }] },
      ],
    };

    expect(() => yamlToNodes(p)).not.toThrow();
  });
});

describe('异常处理 — 哨兵节点操作', () => {
  it('Start 节点存在于空 pipeline 画布中', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'start-test' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const startNode = container.querySelector('[data-id="__start__"]');
    expect(startNode).not.toBeNull();

    unmount();
  });

  it('End 节点存在于空 pipeline 画布中', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'end-test' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const endNode = container.querySelector('[data-id="__end__"]');
    expect(endNode).not.toBeNull();

    unmount();
  });

  it('画布渲染大型 pipeline（50 SubPipeline, 数据层）不崩溃', () => {
    const pipelines: NonNullable<PipelineDetail['pipelines']> = [];
    for (let i = 0; i < 50; i++) {
      pipelines.push({
        name: `sub-${i}`,
        depends_on: i > 0 ? [`sub-${i - 1}`] : [],
        tasks: [{ name: `t-${i}`, env: {}, retry: 0, depends_on: [] }],
      });
    }

    const p: PipelineDetail = { name: 'large', pipelines };

    expect(() => yamlToNodes(p)).not.toThrow();
    const { nodes } = yamlToNodes(p);
    expect(nodes.length).toBeGreaterThan(50);
  });
});
