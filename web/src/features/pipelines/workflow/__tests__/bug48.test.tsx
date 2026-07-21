/**
 * Bug #48 RED 测试 — 编辑模式和查看模式渲染不一致
 *
 * 当前 bug 表现：
 *   WorkflowEditor 的 readOnly prop 只禁用交互（拖拽/连线/右键菜单），
 *   但节点视觉渲染不受影响——端口(Handle)、虚线边框、NodeResizer 等编辑态
 *   元素依然可见，与 PipelineGraph 查看模式的简洁渲染严重不一致。
 *
 * RED 测试策略：
 *   1. readOnly=true 时检查节点端口(Handle)应不渲染
 *   2. readOnly=true 时检查节点边框应为实线（非虚线）
 *   3. readOnly=false（编辑模式）端口正常渲染
 */

import { describe, it, expect, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';

describe('Bug #48 — 编辑模式和查看模式渲染一致', () => {
  it('RED: readOnly=true 模式下应隐藏连接端口(Handle)', async () => {
    const { container } = render(
      <WorkflowEditor
        pipeline={{
          name: 'bug48',
          pipelines: [{
            name: 'build',
            depends_on: [],
            tasks: [{ name: 'compile', command: 'echo', env: {}, retry: 0, depends_on: [] }],
          }],
        }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        readOnly={true}
      />,
    );

    // 等待 ReactFlow 渲染完毕
    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeTruthy();
    });

    // 当前 bug：即使 readOnly=true，端口依然渲染 → container 包含 data-handleid 元素
    // 期望：readOnly=true 时，不渲染端口 → 计数为 0
    const handles = container.querySelectorAll('[data-handleid]');
    expect(handles.length).toBe(0);
  });

  it('RED: readOnly=true 时节点边框应为实线（非虚线）', async () => {
    const { container } = render(
      <WorkflowEditor
        pipeline={{
          name: 'bug48',
          pipelines: [{
            name: 'build',
            depends_on: [],
            tasks: [{ name: 'compile', command: 'echo', env: {}, retry: 0, depends_on: [] }],
          }],
        }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        readOnly={true}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow__node')).toBeTruthy();
    });

    // 当前 bug：编辑节点使用 dashed 边框 → 存在虚线边框样式
    // 期望：readOnly=true 时使用 solid 边框
    const nodes = container.querySelectorAll('.react-flow__node');
    nodes.forEach((node) => {
      const borderStyle = (node as HTMLElement).style.border;
      if (borderStyle) {
        expect(borderStyle).not.toContain('dashed');
      }
    });
  });

  it('RED: readOnly=false（编辑模式）端口正常渲染', async () => {
    const { container } = render(
      <WorkflowEditor
        pipeline={{
          name: 'bug48',
          pipelines: [{
            name: 'build',
            depends_on: [],
            tasks: [{ name: 'compile', command: 'echo', env: {}, retry: 0, depends_on: [] }],
          }],
        }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        readOnly={false}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeTruthy();
    });

    // 编辑模式下端口应正常渲染
    const handles = container.querySelectorAll('[data-handleid]');
    expect(handles.length).toBeGreaterThan(0);
  });
});
