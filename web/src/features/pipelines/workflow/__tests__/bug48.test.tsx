/**
 * Bug #48 测试 — 编辑模式和查看模式渲染一致
 *
 * 原始表现：
 *   WorkflowEditor 的 readOnly prop 只禁用交互（拖拽/连线/右键菜单），
 *   但节点视觉渲染不受影响——端口(Handle)、虚线边框、NodeResizer 等编辑态
 *   元素依然可见，与查看模式的简洁渲染不一致。
 *
 * v2 (2026-07) 契约更新：
 *   压力测试发现"只读模式不渲染 Handle"会让 React Flow 失去边锚点，
 *   导致查看模式所有连线消失。因此 Handle 必须保留但透明（isConnectable=false），
 *   本测试改为断言"存在且透明"。
 */

import { describe, it, expect, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';

describe('Bug #48 — 编辑模式和查看模式渲染一致', () => {
  it('readOnly=true 模式保留 Handle（透明不可连接），保证连线可见', async () => {
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

    // v2 (2026-07): Handle 必须存在（边锚点），但视觉透明
    const handles = container.querySelectorAll('[data-handleid]');
    expect(handles.length).toBeGreaterThan(0);
    for (const h of Array.from(handles)) {
      expect((h as HTMLElement).style.opacity).toBe('0');
    }
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
