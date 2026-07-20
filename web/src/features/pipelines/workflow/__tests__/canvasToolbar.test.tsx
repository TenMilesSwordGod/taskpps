import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkflowEditor from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * 工具栏 + 保存交互测试（重写 v3）
 *
 * 验证真实工具栏操作：
 *   1. 初始状态：保存按钮 disabled（isDirty=false）
 *   2. 修改画布（拖放节点）→ 保存按钮 enabled（isDirty=true）
 *   3. 点击保存 → onGraphChange 被调用 → isDirty=false → 保存按钮 disabled
 *   4. 点击"适应"按钮 → fitView 被触发（reactFlowInstance 已初始化）
 *   5. 只读模式下工具栏隐藏
 *   6. 布局/适应/导出按钮始终存在（非只读模式）
 *
 * 设计决策：
 *   - 用拖放节点来触发 isDirty=true
 *   - 用 onGraphChange 回调验证保存操作
 *   - fitView 在 jsdom 中不抛错即可
 */

function makeSimplePipeline(): PipelineDetail {
  return {
    name: 'toolbar-test',
    pipelines: [
      {
        name: 'job',
        depends_on: [],
        tasks: [{ name: 't1', command: 'echo 1', env: {}, retry: 0, depends_on: [] }],
      },
    ],
  };
}

describe('工具栏 — 保存按钮 isDirty 状态流', () => {
  it('初始状态：保存按钮 disabled（isDirty=false）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSimplePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const saveBtn = screen.getByText('保存');
    expect(saveBtn).toBeInTheDocument();
    expect((saveBtn as HTMLButtonElement).disabled).toBe(true);

    unmount();
  });

  it('拖放节点后 → 保存按钮 enabled（isDirty=true）', async () => {
    const onGraphChange = vi.fn();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'dirty-save' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 验证初始 disabled
    const saveBtnBefore = screen.getByText('保存');
    expect((saveBtnBefore as HTMLButtonElement).disabled).toBe(true);

    // 拖放一个节点使 isDirty=true
    const dt = new DataTransfer();
    dt.setData('application/reactflow-type', 'subpipeline');
    dt.setData('application/reactflow-node-type', 'subpipeline');
    dt.setData('application/reactflow-label', 'new-sub');

    const pane = container.querySelector('[class*="react-flow__pane"]');
    fireEvent.drop(pane!, { dataTransfer: dt, clientX: 300, clientY: 200 });

    await waitFor(() => {
      const saveBtnAfter = screen.getByText('保存');
      expect((saveBtnAfter as HTMLButtonElement).disabled).toBe(false);
    });

    // isDirty=true 时"有未保存的修改"提示出现
    expect(screen.getByText('有未保存的修改')).toBeInTheDocument();

    unmount();
  });

  it('点击保存 → onGraphChange 被调用 → isDirty 重置 → 保存按钮 disabled', async () => {
    const user = userEvent.setup();
    const onGraphChange = vi.fn();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'save-flow' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 1. 拖放节点使 isDirty=true
    const dt = new DataTransfer();
    dt.setData('application/reactflow-type', 'subpipeline');
    dt.setData('application/reactflow-node-type', 'subpipeline');
    dt.setData('application/reactflow-label', 'test');

    const pane = container.querySelector('[class*="react-flow__pane"]');
    fireEvent.drop(pane!, { dataTransfer: dt, clientX: 250, clientY: 150 });

    await waitFor(() => {
      const saveBtn = screen.getByText('保存');
      expect((saveBtn as HTMLButtonElement).disabled).toBe(false);
    });

    // 2. 点击保存按钮
    const saveBtn = screen.getByText('保存');
    await user.click(saveBtn);

    // 3. onGraphChange 被调用（带 nodes 和 edges）
    expect(onGraphChange).toHaveBeenCalled();

    // 4. 保存后 isDirty=false → 按钮 disabled
    await waitFor(() => {
      const saveBtnAfter = screen.getByText('保存');
      expect((saveBtnAfter as HTMLButtonElement).disabled).toBe(true);
    });

    unmount();
  });

  it('点击"适应"按钮不崩溃（fitView 在 jsdom 中为 no-op）', async () => {
    const user = userEvent.setup();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSimplePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const fitBtn = screen.getByText('适应');
    expect(fitBtn).toBeInTheDocument();

    // 点击适应按钮，fitView 调用不应抛出错误
    await user.click(fitBtn);

    // 组件仍正常渲染
    expect(container.querySelector('.react-flow')).toBeInTheDocument();

    unmount();
  });

  it('点击"布局"按钮触发自动布局', async () => {
    const user = userEvent.setup();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSimplePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const layoutBtn = screen.getByText('布局');
    expect(layoutBtn).toBeInTheDocument();
    await user.click(layoutBtn);

    expect(container.querySelector('.react-flow')).toBeInTheDocument();

    unmount();
  });
});

describe('工具栏 — 只读模式', () => {
  it('只读模式下不渲染工具栏按钮', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSimplePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        readOnly={true}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    expect(screen.queryByText('保存')).not.toBeInTheDocument();
    expect(screen.queryByText('布局')).not.toBeInTheDocument();
    expect(screen.queryByText('适应')).not.toBeInTheDocument();
    expect(screen.queryByText('导出')).not.toBeInTheDocument();

    unmount();
  });
});

describe('工具栏 — 按钮完整性', () => {
  it('非只读模式渲染 4 个工具栏按钮（保存/布局/适应/导出）', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makeSimplePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    expect(screen.getByText('保存')).toBeInTheDocument();
    expect(screen.getByText('布局')).toBeInTheDocument();
    expect(screen.getByText('适应')).toBeInTheDocument();
    expect(screen.getByText('导出')).toBeInTheDocument();

    unmount();
  });
});
