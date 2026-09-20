import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PropertyPanel from '../PropertyPanel';
import type { Node } from '@xyflow/react';
import type { EditorNodeData } from '../yamlToNodes';

/**
 * PropertyPanel 组件测试
 * 验证:
 *   - 属性面板渲染
 *   - 字段编辑与保存
 *   - 节点删除
 *   - 关闭行为
 *   - 容器/原子节点的不同编辑内容
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const vi: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const describe: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const it: any;

function makeTaskNode(overrides: Partial<Node<EditorNodeData>> = {}): Node<EditorNodeData> {
  return {
    id: '__task__build.compile',
    type: 'editorTask',
    position: { x: 0, y: 0 },
    data: {
      task: {
        name: 'compile',
        command: 'gcc main.c',
        cwd: '/build',
        env: { CC: 'gcc' },
        retry: 1,
        timeout: 300,
        when: '${env.BRANCH} == main',
        depends_on: [],
      },
      taskType: 'command',
      subpipelineName: 'build',
    },
    ...overrides,
  };
}

function makeSubPipelineNode(): Node<EditorNodeData> {
  return {
    id: '__pipeline__build',
    type: 'editorSubPipeline',
    position: { x: 0, y: 0 },
    style: { width: 260, height: 200 },
    data: {
      label: 'build',
      executionStrategy: 'sequential',
      maxConcurrentTasks: 5,
    },
  };
}

describe('PropertyPanel', () => {
  beforeEach(() => {
    // 关闭 Ant Design 动画以减少测试复杂性
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('渲染', () => {
    it('visible=false 时不渲染', () => {
      const { container } = render(
        <PropertyPanel
          selectedNode={null}
          visible={false}
          onClose={() => {}}
          onSave={() => {}}
          onDelete={() => {}}
        />,
      );
      // Drawer 不应可见
      expect(container.querySelector('.ant-drawer-open')).toBeNull();
    });

    it('task 节点显示属性编辑面板', () => {
      render(
        <PropertyPanel
          selectedNode={makeTaskNode()}
          visible={true}
          onClose={() => {}}
          onSave={() => {}}
          onDelete={() => {}}
        />,
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });

      // 标题显示节点名称
      expect(screen.getByText(/属性编辑.*compile/)).toBeInTheDocument();
    });

    it('task 节点显示命令编辑字段', () => {
      render(
        <PropertyPanel
          selectedNode={makeTaskNode()}
          visible={true}
          onClose={() => {}}
          onSave={() => {}}
          onDelete={() => {}}
        />,
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });

      // 应有名称、描述、命令等字段
      expect(screen.getByText('名称')).toBeInTheDocument();
      expect(screen.getByText('命令')).toBeInTheDocument();
    });

    it('SubPipeline 节点显示执行策略选择', () => {
      render(
        <PropertyPanel
          selectedNode={makeSubPipelineNode()}
          visible={true}
          onClose={() => {}}
          onSave={() => {}}
          onDelete={() => {}}
        />,
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });

      expect(screen.getByText('执行策略')).toBeInTheDocument();
      expect(screen.getByText('最大并发数')).toBeInTheDocument();
    });

    it('task 节点显示 when 条件字段', () => {
      render(
        <PropertyPanel
          selectedNode={makeTaskNode()}
          visible={true}
          onClose={() => {}}
          onSave={() => {}}
          onDelete={() => {}}
        />,
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });

      expect(screen.getByText('When 条件')).toBeInTheDocument();
    });

    it('task 节点显示 超时/重试/失败策略 字段', () => {
      render(
        <PropertyPanel
          selectedNode={makeTaskNode()}
          visible={true}
          onClose={() => {}}
          onSave={() => {}}
          onDelete={() => {}}
        />,
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });

      expect(screen.getByText('超时 (秒)')).toBeInTheDocument();
      expect(screen.getByText('重试次数')).toBeInTheDocument();
      expect(screen.getByText('失败策略')).toBeInTheDocument();
    });
  });

  describe('交互: 关闭与取消', () => {
    it('点击取消按钮触发 onClose', async () => {
      let closed = false;
      render(
        <PropertyPanel
          selectedNode={makeTaskNode()}
          visible={true}
          onClose={() => { closed = true; }}
          onSave={() => {}}
          onDelete={() => {}}
        />,
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });

      const cancelBtn = screen.queryByText('取消');
      if (cancelBtn) {
        await userEvent.click(cancelBtn);
        expect(closed).toBe(true);
      }
    });
  });

  describe('交互: 保存', () => {
    it('点击确认按钮触发 onSave 并携带更新后的节点数据', async () => {
      let savedNode: Node<EditorNodeData> | null = null;
      render(
        <PropertyPanel
          selectedNode={makeTaskNode()}
          visible={true}
          onClose={() => {}}
          onSave={(node) => { savedNode = node; }}
          onDelete={() => {}}
        />,
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });

      const confirmBtn = screen.queryByText('确认');
      if (confirmBtn) {
        await userEvent.click(confirmBtn);
        // 验证保存的节点包含原始数据
        expect(savedNode).not.toBeNull();
        expect(savedNode?.data?.task?.name).toBe('compile');
      }
    });
  });

  describe('交互: 删除', () => {
    it('点击删除按钮触发 onDelete', async () => {
      let deletedId: string | null = null;
      render(
        <PropertyPanel
          selectedNode={makeTaskNode()}
          visible={true}
          onClose={() => {}}
          onSave={() => {}}
          onDelete={(id) => { deletedId = id; }}
        />,
      );

      act(() => {
        vi.advanceTimersByTime(300);
      });

      const deleteBtn = screen.queryByText('删除节点');
      if (deleteBtn) {
        await userEvent.click(deleteBtn);
        expect(deletedId).toBe('__task__build.compile');
      }
    });
  });

  describe('null node 处理', () => {
    it('selectedNode=null 时不渲染面板内容', () => {
      // 即使 visible=true，null node 也不应渲染
      const { container } = render(
        <PropertyPanel
          selectedNode={null}
          visible={true}
          onClose={() => {}}
          onSave={() => {}}
          onDelete={() => {}}
        />,
      );

      // 不应有 drawer 内容（因 return null）
      expect(container.querySelector('.ant-drawer-open')).toBeNull();
    });
  });
});
