import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, waitFor, fireEvent, screen, cleanup } from '@testing-library/react';
import WorkflowEditor, { type WorkflowEditorRef } from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * bug #35 修复验证：
 * 通过 forwardRef 暴露的 deleteNode 删除节点后，
 * onGraphChange 必须收到不含被删节点的新 nodes/edges，
 * 以证明父组件 editNodes/editEdges 实时同步（不会保存时"复活"节点）。
 *
 * v6 (2026-08): critique P1 删除守卫适配 ——
 *   - __pipeline__ 升级为不可删哨兵（与键盘路径行为一致），删除目标改用普通任务节点；
 *   - deleteNode 需经确认弹窗（点击「确认删除」后才执行），故用例中补确认交互。
 */

function makeDeleteSyncPipeline(): PipelineDetail {
  return {
    name: 'delete-sync',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [{ name: 'compile', command: 'make', env: {}, retry: 0, depends_on: [] }],
      },
    ],
  };
}

describe('WorkflowEditor onGraphChange 同步 (bug #35)', () => {
  afterEach(() => {
    cleanup();
    // v6 (2026-08): 删除确认 Modal 渲染在 body portal，跨用例清理防污染
    document
      .querySelectorAll('.ant-modal-root, .ant-modal-mask, .ant-modal-wrap')
      .forEach((el) => el.remove());
  });

  it('删除节点后 onGraphChange 收到的新 nodes 不含被删节点', async () => {
    const onGraphChange = vi.fn();
    let refValue: WorkflowEditorRef | null = null;

    const { container, unmount } = render(
      <WorkflowEditor
        ref={(r) => {
          refValue = r;
        }}
        pipeline={makeDeleteSyncPipeline()}
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

    // 删除普通任务节点 → 经确认弹窗后执行
    refValue!.deleteNode('__task__build.compile');
    await waitFor(() =>
      expect(document.querySelector('.ant-modal-confirm-title')).not.toBeNull(),
    );
    fireEvent.click(screen.getByRole('button', { name: /确认删除/ }));

    expect(onGraphChange).toHaveBeenCalled();

    // 取最后一次回传，验证被删节点确实不在新图中
    const lastCall = onGraphChange.mock.calls[onGraphChange.mock.calls.length - 1];
    const newNodes = lastCall[0] as { id: string }[];
    const newEdges = lastCall[1] as { source: string; target: string }[];

    expect(newNodes.find((n) => n.id === '__task__build.compile')).toBeUndefined();
    expect(
      newEdges.every(
        (e) => e.source !== '__task__build.compile' && e.target !== '__task__build.compile',
      ),
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
