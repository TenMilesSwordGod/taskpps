import { describe, it, expect, vi } from 'vitest';
import { createRef } from 'react';
import { render, waitFor, fireEvent } from '@testing-library/react';
import WorkflowEditor, { type WorkflowEditorRef } from '../WorkflowEditor';

/**
 * bug #35 修复验证：
 * 通过 forwardRef 暴露的 deleteNode 删除节点后，
 * onGraphChange 必须收到不含被删节点的新 nodes/edges，
 * 以证明父组件 editNodes/editEdges 实时同步（不会保存时"复活"节点）。
 */

describe('WorkflowEditor onGraphChange 同步 (bug #35)', () => {
  it('删除节点后 onGraphChange 收到的新 nodes 不含被删节点', async () => {
    const onGraphChange = vi.fn();
    const ref = createRef<WorkflowEditorRef>();

    const { container, unmount } = render(
      <WorkflowEditor
        ref={ref}
        pipeline={{ name: 'delete-sync' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    // 等待 React Flow 渲染完成
    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 关键断言：初始挂载阶段不应触发 onGraphChange（同步只在图变更时发生）
    expect(onGraphChange).not.toHaveBeenCalled();

    // 通过 PropertyPanel 删除路径（forwardRef.deleteNode）删除初始 __pipeline__ 节点
    ref.current?.deleteNode('__pipeline__');

    expect(onGraphChange).toHaveBeenCalled();

    // 取最后一次回传，验证被删节点确实不在新图中
    const lastCall = onGraphChange.mock.calls[onGraphChange.mock.calls.length - 1];
    const newNodes = lastCall[0] as { id: string }[];
    const newEdges = lastCall[1] as { source: string; target: string }[];

    expect(newNodes.find((n) => n.id === '__pipeline__')).toBeUndefined();
    expect(
      newEdges.every((e) => e.source !== '__pipeline__' && e.target !== '__pipeline__'),
    ).toBe(true);

    unmount();
  });

  it('新增节点（拖放路径）后 onGraphChange 收到含新节点的新图', async () => {
    const onGraphChange = vi.fn();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'add-sync' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 模拟从 NodePalette 拖入一个 SubPipeline 节点
    const dt = new DataTransfer();
    dt.setData('application/reactflow-type', 'subpipeline');
    dt.setData('application/reactflow-node-type', 'subpipeline');
    dt.setData('application/reactflow-label', 'ci');

    const pane = container.querySelector('[class*="react-flow__pane"]');
    expect(pane).not.toBeNull();
    fireEvent.drop(pane!, { dataTransfer: dt, clientX: 200, clientY: 150 });

    expect(onGraphChange).toHaveBeenCalled();
    const lastCall = onGraphChange.mock.calls[onGraphChange.mock.calls.length - 1];
    const newNodes = lastCall[0] as { type?: string }[];
    expect(newNodes.some((n) => n.type === 'editorSubPipeline')).toBe(true);

    unmount();
  });
});
