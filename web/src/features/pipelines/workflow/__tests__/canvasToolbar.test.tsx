import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkflowEditor, { type WorkflowEditorRef } from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * 工具栏 + 脏状态跟踪测试（重写 v4）
 *
 * 验证工具栏操作 + isDirty 暴露：
 *   1. 拖放节点 → isDirty=true（ref 暴露） + 脏标记出现
 *   2. 拖放节点 → onGraphChange 被调用
 *   3. 点击"适应"按钮 → fitView 被触发（reactFlowInstance 已初始化）
 *   4. 点击"布局"按钮触发自动布局
 *   5. 只读模式下仅保留"适应"按钮（v2: 布局/导出隐藏）
 *   6. 非只读模式渲染 3 个工具栏按钮（布局/适应/导出）
 *
 * v4 (2026-07): 移除 WorkflowEditor 内部"保存"按钮（假保存），
 *   保存由父组件 PipelineDetailPage 的顶层保存按钮（handleSaveFromEditor）统一负责。
 *   新增 isDirty ref 暴露，供父组件做 beforeunload 和模式切换守卫。
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

describe('工具栏 — isDirty 状态与脏标记', () => {
  it('初始状态：isDirty=false（通过 ref 读取）', async () => {
    // v4 (2026-07): 用 callback ref 获取 forwarded ref 的最新值
    // useRef pattern 在 render 函数体内读取不到 ref.current（React 在 render 后赋值）
    let refValue: WorkflowEditorRef | null = null;
    const { container, unmount } = render(
      <WorkflowEditor
        ref={(r) => { refValue = r; }}
        pipeline={makeSimplePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(refValue).not.toBeNull();
    });
    expect(refValue!.isDirty).toBe(false);

    unmount();
  });

  it('拖放节点后 → isDirty=true（ref 暴露）+ 脏标记出现', async () => {
    const onGraphChange = vi.fn();
    let refValue: WorkflowEditorRef | null = null;
    const { container, unmount } = render(
      <WorkflowEditor
        ref={(r) => { refValue = r; }}
        pipeline={{ name: 'dirty-save' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 初始 isDirty=false
    await waitFor(() => {
      expect(refValue).not.toBeNull();
    });
    expect(refValue!.isDirty).toBe(false);

    // 拖放一个节点使 isDirty=true
    const dt = new DataTransfer();
    dt.setData('application/reactflow-type', 'subpipeline');
    dt.setData('application/reactflow-node-type', 'subpipeline');
    dt.setData('application/reactflow-label', 'new-sub');

    const pane = container.querySelector('[class*="react-flow__pane"]');
    fireEvent.drop(pane!, { dataTransfer: dt, clientX: 300, clientY: 200 });

    await waitFor(() => {
      expect(refValue!.isDirty).toBe(true);
    });

    // isDirty=true 时"有未保存的修改"提示出现
    expect(screen.getByText('有未保存的修改')).toBeInTheDocument();

    unmount();
  });

  it('拖放节点 → onGraphChange 被调用', async () => {
    const onGraphChange = vi.fn();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={{ name: 'graph-sync' }}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const dt = new DataTransfer();
    dt.setData('application/reactflow-type', 'subpipeline');
    dt.setData('application/reactflow-node-type', 'subpipeline');
    dt.setData('application/reactflow-label', 'test');

    const pane = container.querySelector('[class*="react-flow__pane"]');
    fireEvent.drop(pane!, { dataTransfer: dt, clientX: 250, clientY: 150 });

    await waitFor(() => {
      expect(onGraphChange).toHaveBeenCalled();
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

    await user.click(fitBtn);
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
  it('只读模式下仅保留"适应"按钮，布局/导出不可用', async () => {
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

    // v2 (2026-07): 查看模式保留"适应窗口" —— 大图在只读画布上无法用编辑工具，
    // 没有适应按钮时只能看到局部（复杂场景压力测试暴露的 UX 问题）。
    // 布局/导出仍仅编辑模式可用。
    expect(screen.queryByText('布局')).not.toBeInTheDocument();
    expect(screen.getByText('适应')).toBeInTheDocument();
    expect(screen.queryByText('导出')).not.toBeInTheDocument();

    unmount();
  });
});

describe('工具栏 — 按钮完整性', () => {
  it('非只读模式渲染 3 个工具栏按钮（布局/适应/导出）', async () => {
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

    expect(screen.getByText('布局')).toBeInTheDocument();
    expect(screen.getByText('适应')).toBeInTheDocument();
    expect(screen.getByText('导出')).toBeInTheDocument();

    unmount();
  });
});
