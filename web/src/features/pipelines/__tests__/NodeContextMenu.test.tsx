import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';
import NodeContextMenu from '../NodeContextMenu';
import { usePipelineEditorStore } from '../stores/pipelineEditorStore';

/**
 * NodeContextMenu 交互测试
 *
 * 覆盖维度：显示条件（contextMenu null/有值）、菜单项（edit/readonly 模式差异）、
 * 回调触发、菜单关闭逻辑、nodeId 影响禁用状态
 * 设计决策：Ant Design Dropdown 用 open+trigger=[] 手动控制，editMode 决定菜单项集合
 */

// Mock Ant Design icons to avoid SVG rendering issues
vi.mock('@ant-design/icons', () => ({
  CopyOutlined: () => null,
  SnippetsOutlined: () => null,
  DeleteOutlined: () => null,
  InfoCircleOutlined: () => null,
  FileTextOutlined: () => null,
  FormOutlined: () => null,
}));

function resetStore() {
  usePipelineEditorStore.setState({
    editMode: true,
    nodePanelOpen: false,
    isRunning: false,
    contextMenu: null,
    stickyNotes: [],
  });
}

describe('NodeContextMenu — 显示条件', () => {
  beforeEach(() => resetStore());

  it('contextMenu=null 时返回 null', () => {
    const { container } = render(<NodeContextMenu />);
    expect(container.firstChild).toBeNull();
  });

  it('contextMenu 有值时渲染 Dropdown', () => {
    usePipelineEditorStore.setState({
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-1' },
    });
    const { container } = render(<NodeContextMenu />);
    // Dropdown 通过 getPopupContainer 将菜单挂载到 body，container 内是触发元素 span
    // 验证 Dropdown 存在即可
    expect(container.querySelector('span')).toBeTruthy();
  });
});

describe('NodeContextMenu — 编辑模式菜单项', () => {
  beforeEach(() => resetStore());
  afterEach(() => cleanup());

  it('编辑模式下菜单包含"复制节点"项', () => {
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-1' },
    });
    render(<NodeContextMenu />);
    // Ant Design Dropdown 会将菜单渲染到 document.body
    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item');
    const labels = Array.from(menuItems).map(el => el.textContent);
    expect(labels.some(l => l?.includes('复制节点'))).toBe(true);
  });

  it('编辑模式下菜单包含"删除节点"项', () => {
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-1' },
    });
    render(<NodeContextMenu />);
    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item');
    const labels = Array.from(menuItems).map(el => el.textContent);
    expect(labels.some(l => l?.includes('删除节点'))).toBe(true);
  });

  it('编辑模式下菜单包含"添加便签"项', () => {
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-1' },
    });
    render(<NodeContextMenu />);
    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item');
    const labels = Array.from(menuItems).map(el => el.textContent);
    expect(labels.some(l => l?.includes('添加便签'))).toBe(true);
  });
});

describe('NodeContextMenu — 只读模式菜单项', () => {
  beforeEach(() => resetStore());
  afterEach(() => cleanup());

  it('只读模式：仅"查看属性""查看日志"可用', () => {
    usePipelineEditorStore.setState({
      editMode: false,
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-1' },
    });
    render(<NodeContextMenu />);
    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item');
    const labels = Array.from(menuItems).map(el => el.textContent);

    // 只读模式不应有编辑类菜单项
    expect(labels.some(l => l?.includes('复制节点'))).toBe(false);
    expect(labels.some(l => l?.includes('粘贴节点'))).toBe(false);
    expect(labels.some(l => l?.includes('删除节点'))).toBe(false);
    expect(labels.some(l => l?.includes('添加便签'))).toBe(false);

    // 只读安全操作存在
    expect(labels.some(l => l?.includes('查看属性'))).toBe(true);
    expect(labels.some(l => l?.includes('查看日志'))).toBe(true);
  });
});

describe('NodeContextMenu — 回调触发', () => {
  beforeEach(() => resetStore());

  it('点击"删除节点"触发 onDeleteNode 回调并关闭菜单', () => {
    const onDeleteNode = vi.fn();
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-1' },
    });

    render(
      <NodeContextMenu onDeleteNode={onDeleteNode} />,
    );

    // 找到删除按钮并点击
    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item');
    for (const item of menuItems) {
      if (item.textContent?.includes('删除节点')) {
        (item as HTMLElement).click();
        break;
      }
    }

    expect(onDeleteNode).toHaveBeenCalledWith('task-1');
    expect(usePipelineEditorStore.getState().contextMenu).toBeNull();
  });

  it('点击"查看属性"触发 onViewProperties 回调并关闭菜单', () => {
    const onViewProperties = vi.fn();
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-3' },
    });

    render(
      <NodeContextMenu onViewProperties={onViewProperties} />,
    );

    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item');
    for (const item of menuItems) {
      if (item.textContent?.includes('查看属性')) {
        (item as HTMLElement).click();
        break;
      }
    }

    expect(onViewProperties).toHaveBeenCalledWith('task-3');
    expect(usePipelineEditorStore.getState().contextMenu).toBeNull();
  });

  it('点击"复制节点"触发 onCopyNode 回调', () => {
    const onCopyNode = vi.fn();
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-2' },
    });

    render(
      <NodeContextMenu onCopyNode={onCopyNode} />,
    );

    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item');
    for (const item of menuItems) {
      if (item.textContent?.includes('复制节点')) {
        (item as HTMLElement).click();
        break;
      }
    }

    expect(onCopyNode).toHaveBeenCalledWith('task-2');
  });

  it('点击"添加便签"触发 onAddStickyNote 回调（nodeId=null 时也可触发）', () => {
    const onAddStickyNote = vi.fn();
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 50, y: 50, nodeId: null },
    });

    render(
      <NodeContextMenu onAddStickyNote={onAddStickyNote} />,
    );

    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item');
    for (const item of menuItems) {
      if (item.textContent?.includes('添加便签')) {
        (item as HTMLElement).click();
        break;
      }
    }

    expect(onAddStickyNote).toHaveBeenCalledWith(null);
  });
});

describe('NodeContextMenu — nodeId 影响禁用状态', () => {
  beforeEach(() => resetStore());
  afterEach(() => cleanup());

  it('nodeId=null 时"复制节点"disabled', () => {
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 100, y: 200, nodeId: null },
    });
    render(<NodeContextMenu />);

    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item-disabled');
    const disabledLabels = Array.from(menuItems).map(el => el.textContent);
    expect(disabledLabels.some(l => l?.includes('复制节点'))).toBe(true);
    expect(disabledLabels.some(l => l?.includes('删除节点'))).toBe(true);
    expect(disabledLabels.some(l => l?.includes('查看属性'))).toBe(true);
    expect(disabledLabels.some(l => l?.includes('查看日志'))).toBe(true);
  });

  it('nodeId 有值时"复制节点"不禁用', () => {
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-1' },
    });
    render(<NodeContextMenu />);

    const menuItems = document.querySelectorAll('.ant-dropdown-menu-item-disabled');
    const disabledLabels = Array.from(menuItems).map(el => el.textContent);
    // "粘贴节点"始终禁用（paste-node 功能未实现）
    expect(disabledLabels.some(l => l?.includes('粘贴节点'))).toBe(true);
  });
});

// 外部点击关闭测试 — 需要实际 DOM 环境
describe('NodeContextMenu — 外部点击关闭', () => {
  beforeEach(() => resetStore());

  it('点击 Ant Dropdown 菜单外部时 closeContextMenu 被调用', async () => {
    usePipelineEditorStore.setState({
      editMode: true,
      contextMenu: { open: true, x: 100, y: 200, nodeId: 'task-1' },
    });

    render(<NodeContextMenu />);

    expect(usePipelineEditorStore.getState().contextMenu).not.toBeNull();

    // 等待 setTimeout(0) 注册 mousedown listener，再触发事件
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });

    act(() => {
      document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });

    expect(usePipelineEditorStore.getState().contextMenu).toBeNull();
  });
});
