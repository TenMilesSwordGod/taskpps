import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import NodePanel from '../NodePanel';
import { usePipelineEditorStore } from '../stores/pipelineEditorStore';

/**
 * NodePanel 交互测试
 *
 * 覆盖维度：渲染/显示条件、拖拽启动 MIME type、分组与节点类型完整性、搜索输入存在性、折叠按钮
 * 设计决策：NodePanel 在 editMode=false 或 nodePanelOpen=false 时返回 null
 */

function resetStore() {
  usePipelineEditorStore.setState({
    editMode: true,
    nodePanelOpen: true,
    isRunning: false,
    contextMenu: null,
    stickyNotes: [],
  });
}

describe('NodePanel — 渲染条件', () => {
  beforeEach(() => {
    usePipelineEditorStore.setState({
      editMode: true,
      nodePanelOpen: true,
      isRunning: false,
      contextMenu: null,
      stickyNotes: [],
    });
  });

  it('editMode=true 且 nodePanelOpen=true 时渲染面板', () => {
    const { container } = render(<NodePanel />);
    expect(container.firstChild).toBeTruthy();
  });

  it('editMode=false 时返回 null', () => {
    usePipelineEditorStore.setState({ editMode: false, nodePanelOpen: true });
    const { container } = render(<NodePanel />);
    expect(container.firstChild).toBeNull();
  });

  it('nodePanelOpen=false 时返回 null', () => {
    usePipelineEditorStore.setState({ editMode: true, nodePanelOpen: false });
    const { container } = render(<NodePanel />);
    expect(container.firstChild).toBeNull();
  });
});

describe('NodePanel — 面板内容', () => {
  beforeEach(() => resetStore());

  it('面板标题"节点面板"渲染', () => {
    render(<NodePanel />);
    expect(screen.getByText('节点面板')).toBeInTheDocument();
  });

  it('3 个分组标题渲染（v2 2026-07: git 归入 plugin 子类型，减少为 3 组）', () => {
    render(<NodePanel />);
    expect(screen.getByText('命令与调用')).toBeInTheDocument();
    expect(screen.getByText('步骤与插件')).toBeInTheDocument();
    expect(screen.getByText('仓库与远程')).toBeInTheDocument();
  });

  it('6 种 Task 类型全部渲染（v2 2026-07: git 已归入 plugin 子类型）', () => {
    render(<NodePanel />);
    expect(screen.getByText('命令')).toBeInTheDocument();
    expect(screen.getByText('调用')).toBeInTheDocument();
    expect(screen.getByText('步骤')).toBeInTheDocument();
    expect(screen.getByText('插件')).toBeInTheDocument();
    expect(screen.getByText('Nexus')).toBeInTheDocument();
    expect(screen.getByText('SSH')).toBeInTheDocument();
  });

  it('折叠按钮存在（ChevronLeft 图标）', () => {
    const { container } = render(<NodePanel />);
    const buttons = container.querySelectorAll('button');
    const closeBtn = Array.from(buttons).find(b => b.querySelector('svg'));
    expect(closeBtn).toBeTruthy();
  });

  it('搜索输入框存在', () => {
    render(<NodePanel />);
    expect(screen.getByPlaceholderText('搜索节点...')).toBeInTheDocument();
  });
});

describe('NodePanel — 拖拽交互', () => {
  beforeEach(() => resetStore());

  it('拖拽"命令"节点时设置 application/reactflow MIME type 数据', () => {
    render(<NodePanel />);
    const commandItem = screen.getByText('命令').closest('[draggable]')!;
    const dataTransfer: Record<string, string> = {};

    fireEvent.dragStart(commandItem, {
      dataTransfer: {
        setData: (type: string, value: string) => {
          dataTransfer[type] = value;
        },
        effectAllowed: '',
      },
    });

    const payload = JSON.parse(dataTransfer['application/reactflow']);
    expect(payload.taskType).toBe('command');
    expect(payload.label).toBe('命令');
    expect(payload.color).toBe('#4C6EF5');
  });

  it('拖拽"SSH"节点时 MIME 数据正确', () => {
    render(<NodePanel />);
    const sshItem = screen.getByText('SSH').closest('[draggable]')!;
    const dataTransfer: Record<string, string> = {};

    fireEvent.dragStart(sshItem, {
      dataTransfer: {
        setData: (type: string, value: string) => {
          dataTransfer[type] = value;
        },
        effectAllowed: '',
      },
    });

    const payload = JSON.parse(dataTransfer['application/reactflow']);
    expect(payload.taskType).toBe('ssh');
    expect(payload.label).toBe('SSH');
    expect(payload.color).toBe('#74B816');
  });

  it('拖拽所有 6 种节点类型 MIME type 均为 application/reactflow（v2: git 已归入 plugin）', () => {
    render(<NodePanel />);
    const labels = ['命令', '调用', '步骤', '插件', 'Nexus', 'SSH'];

    for (const label of labels) {
      const item = screen.getByText(label).closest('[draggable]')!;
      const dataTransfer: Record<string, string> = {};

      fireEvent.dragStart(item, {
        dataTransfer: {
          setData: (type: string, value: string) => {
            dataTransfer[type] = value;
          },
          effectAllowed: '',
        },
      });

      expect(dataTransfer['application/reactflow']).toBeTruthy();
      const payload = JSON.parse(dataTransfer['application/reactflow']);
      expect(payload).toHaveProperty('taskType');
      expect(payload).toHaveProperty('label');
      expect(payload).toHaveProperty('color');
    }
  });
});

describe('NodePanel — 搜索输入', () => {
  beforeEach(() => resetStore());

  it('搜索框可以输入文本', () => {
    render(<NodePanel />);
    const input = screen.getByPlaceholderText('搜索节点...') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'command' } });
    expect(input.value).toBe('command');
  });

  it('搜索框输入空字符串', () => {
    render(<NodePanel />);
    const input = screen.getByPlaceholderText('搜索节点...') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '' } });
    expect(input.value).toBe('');
  });
});

describe('NodePanel — 边界情况', () => {
  beforeEach(() => resetStore());

  it('面板宽度为 260px', () => {
    const { container } = render(<NodePanel />);
    const panel = container.firstChild as HTMLElement;
    expect(panel.style.width).toBe('260px');
  });

  it('面板背景色为深色 #1A1B1E', () => {
    const { container } = render(<NodePanel />);
    const panel = container.firstChild as HTMLElement;
    expect(panel.style.backgroundColor).toBe('rgb(26, 27, 30)'); // #1A1B1E
  });

  it('每个可拖拽条目有 draggable 属性（v2: 6 种类型）', () => {
    render(<NodePanel />);
    const draggableItems = screen.getAllByText((content) =>
      ['命令', '调用', '步骤', '插件', 'Nexus', 'SSH'].includes(content),
    );
    expect(draggableItems).toHaveLength(6);
  });
});
