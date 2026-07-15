import { describe, it, expect, beforeEach } from 'vitest';
import { usePipelineEditorStore, STICKY_COLORS } from '../stores/pipelineEditorStore';
import type { StickyColor } from '../stores/pipelineEditorStore';

/**
 * pipelineEditorStore 状态机测试
 *
 * 覆盖维度：编辑模式切换、运行态锁定、面板联动、右键菜单、便签 CRUD
 * 测试策略：纯 Zustand store 单测，不依赖 React 组件渲染，保证状态转换逻辑正确
 */

function resetStore() {
  usePipelineEditorStore.setState({
    editMode: false,
    nodePanelOpen: false,
    isRunning: false,
    contextMenu: null,
    stickyNotes: [],
  });
}

describe('pipelineEditorStore — 编辑模式与运行态', () => {
  beforeEach(() => resetStore());

  it('初始状态：editMode=false, nodePanelOpen=false, isRunning=false', () => {
    const s = usePipelineEditorStore.getState();
    expect(s.editMode).toBe(false);
    expect(s.nodePanelOpen).toBe(false);
    expect(s.isRunning).toBe(false);
    expect(s.contextMenu).toBeNull();
    expect(s.stickyNotes).toEqual([]);
  });

  // --- setEditMode ---

  it('setEditMode(true) 开启编辑模式→自动打开节点面板（N8N 联动逻辑）', () => {
    usePipelineEditorStore.getState().setEditMode(true);
    const s = usePipelineEditorStore.getState();
    expect(s.editMode).toBe(true);
    expect(s.nodePanelOpen).toBe(true);
  });

  it('setEditMode(false) 关闭编辑模式→自动关闭节点面板', () => {
    usePipelineEditorStore.getState().setEditMode(true);
    usePipelineEditorStore.getState().setEditMode(false);
    const s = usePipelineEditorStore.getState();
    expect(s.editMode).toBe(false);
    expect(s.nodePanelOpen).toBe(false);
  });

  // --- isRunning 锁定 ---

  it('setRunning(true) 强制只读模式：editMode=false, nodePanelOpen=false', () => {
    // 先设为编辑模式
    usePipelineEditorStore.getState().setEditMode(true);
    expect(usePipelineEditorStore.getState().editMode).toBe(true);

    // 开始运行
    usePipelineEditorStore.getState().setRunning(true);
    const s = usePipelineEditorStore.getState();
    expect(s.isRunning).toBe(true);
    expect(s.editMode).toBe(false);
    expect(s.nodePanelOpen).toBe(false);
  });

  it('运行中 setEditMode(true) 不生效（被锁定）', () => {
    usePipelineEditorStore.getState().setRunning(true);
    usePipelineEditorStore.getState().setEditMode(true);
    const s = usePipelineEditorStore.getState();
    expect(s.isRunning).toBe(true);
    expect(s.editMode).toBe(false);
  });

  it('setRunning(false) 恢复非运行态，但不自动进入编辑模式', () => {
    usePipelineEditorStore.getState().setRunning(true);
    usePipelineEditorStore.getState().setRunning(false);
    const s = usePipelineEditorStore.getState();
    expect(s.isRunning).toBe(false);
    expect(s.editMode).toBe(false);
    expect(s.nodePanelOpen).toBe(false);
  });

  // --- toggleNodePanel ---

  it('编辑模式下 toggleNodePanel 切换面板开关', () => {
    usePipelineEditorStore.getState().setEditMode(true);
    // 编辑模式默认打开面板
    expect(usePipelineEditorStore.getState().nodePanelOpen).toBe(true);

    usePipelineEditorStore.getState().toggleNodePanel();
    expect(usePipelineEditorStore.getState().nodePanelOpen).toBe(false);

    usePipelineEditorStore.getState().toggleNodePanel();
    expect(usePipelineEditorStore.getState().nodePanelOpen).toBe(true);
  });

  it('只读模式下 toggleNodePanel 不生效', () => {
    expect(usePipelineEditorStore.getState().editMode).toBe(false);
    expect(usePipelineEditorStore.getState().nodePanelOpen).toBe(false);

    usePipelineEditorStore.getState().toggleNodePanel();
    expect(usePipelineEditorStore.getState().nodePanelOpen).toBe(false);
  });

  // --- setNodePanelOpen ---

  it('setNodePanelOpen 直接设置面板状态（不受 editMode 限制）', () => {
    usePipelineEditorStore.getState().setNodePanelOpen(true);
    expect(usePipelineEditorStore.getState().nodePanelOpen).toBe(true);
    usePipelineEditorStore.getState().setNodePanelOpen(false);
    expect(usePipelineEditorStore.getState().nodePanelOpen).toBe(false);
  });
});

describe('pipelineEditorStore — 右键菜单', () => {
  beforeEach(() => resetStore());

  it('初始 contextMenu=null', () => {
    expect(usePipelineEditorStore.getState().contextMenu).toBeNull();
  });

  it('setContextMenu 设置菜单状态', () => {
    const menu = { open: true, x: 100, y: 200, nodeId: 'task-1' };
    usePipelineEditorStore.getState().setContextMenu(menu);
    expect(usePipelineEditorStore.getState().contextMenu).toEqual(menu);
  });

  it('closeContextMenu 重置为 null', () => {
    usePipelineEditorStore.getState().setContextMenu({ open: true, x: 0, y: 0, nodeId: null });
    usePipelineEditorStore.getState().closeContextMenu();
    expect(usePipelineEditorStore.getState().contextMenu).toBeNull();
  });

  it('setContextMenu(null) 关闭菜单', () => {
    usePipelineEditorStore.getState().setContextMenu({ open: true, x: 0, y: 0, nodeId: 'node-1' });
    usePipelineEditorStore.getState().setContextMenu(null);
    expect(usePipelineEditorStore.getState().contextMenu).toBeNull();
  });
});

describe('pipelineEditorStore — 便签 CRUD', () => {
  beforeEach(() => resetStore());

  const sampleNote = {
    id: 'note-1',
    position: { x: 100, y: 200 },
    content: '测试便签',
    color: 'yellow' as StickyColor,
    width: 240,
    height: 160,
    snapToNodeId: null as string | null,
  };

  it('addStickyNote 添加便签', () => {
    usePipelineEditorStore.getState().addStickyNote(sampleNote);
    expect(usePipelineEditorStore.getState().stickyNotes).toHaveLength(1);
    expect(usePipelineEditorStore.getState().stickyNotes[0]).toEqual(sampleNote);
  });

  it('addStickyNote 多次添加顺序追加', () => {
    usePipelineEditorStore.getState().addStickyNote(sampleNote);
    usePipelineEditorStore.getState().addStickyNote({ ...sampleNote, id: 'note-2' });
    const notes = usePipelineEditorStore.getState().stickyNotes;
    expect(notes).toHaveLength(2);
    expect(notes[0].id).toBe('note-1');
    expect(notes[1].id).toBe('note-2');
  });

  it('removeStickyNote 删除指定便签', () => {
    usePipelineEditorStore.getState().addStickyNote(sampleNote);
    usePipelineEditorStore.getState().addStickyNote({ ...sampleNote, id: 'note-2' });
    usePipelineEditorStore.getState().removeStickyNote('note-1');
    const notes = usePipelineEditorStore.getState().stickyNotes;
    expect(notes).toHaveLength(1);
    expect(notes[0].id).toBe('note-2');
  });

  it('removeStickyNote 不存在的 id 不影响列表', () => {
    usePipelineEditorStore.getState().addStickyNote(sampleNote);
    usePipelineEditorStore.getState().removeStickyNote('not-exist');
    expect(usePipelineEditorStore.getState().stickyNotes).toHaveLength(1);
  });

  it('updateStickyNote 部分更新便签字段', () => {
    usePipelineEditorStore.getState().addStickyNote(sampleNote);
    usePipelineEditorStore.getState().updateStickyNote('note-1', { content: '更新内容', color: 'blue' });
    const note = usePipelineEditorStore.getState().stickyNotes[0];
    expect(note.content).toBe('更新内容');
    expect(note.color).toBe('blue');
    expect(note.width).toBe(240); // 未修改字段保持不变
  });

  it('updateStickyNote 更新位置和吸附', () => {
    usePipelineEditorStore.getState().addStickyNote(sampleNote);
    usePipelineEditorStore.getState().updateStickyNote('note-1', {
      position: { x: 300, y: 400 },
      snapToNodeId: 'task-5',
    });
    const note = usePipelineEditorStore.getState().stickyNotes[0];
    expect(note.position).toEqual({ x: 300, y: 400 });
    expect(note.snapToNodeId).toBe('task-5');
  });

  it('updateStickyNote 不存在的 id 不影响列表', () => {
    usePipelineEditorStore.getState().addStickyNote(sampleNote);
    usePipelineEditorStore.getState().updateStickyNote('not-exist', { content: 'x' });
    expect(usePipelineEditorStore.getState().stickyNotes[0].content).toBe('测试便签');
  });

  it('STICKY_COLORS 包含 5 种颜色', () => {
    const keys = Object.keys(STICKY_COLORS);
    expect(keys).toHaveLength(5);
    expect(keys).toContain('yellow');
    expect(keys).toContain('blue');
    expect(keys).toContain('green');
    expect(keys).toContain('pink');
    expect(keys).toContain('orange');
  });

  it('STICKY_COLORS 每种颜色包含 bg, border, dot, label', () => {
    for (const [key, colors] of Object.entries(STICKY_COLORS)) {
      expect(colors).toHaveProperty('bg');
      expect(colors).toHaveProperty('border');
      expect(colors).toHaveProperty('dot');
      expect(colors).toHaveProperty('label');
      expect(colors.bg).toMatch(/^#/);
      expect(colors.border).toMatch(/^#/);
      expect(colors.dot).toMatch(/^#/);
    }
  });
});

describe('pipelineEditorStore — 边界与异常', () => {
  beforeEach(() => resetStore());

  it('空便签内容：content="" 允许添加', () => {
    usePipelineEditorStore.getState().addStickyNote({
      id: 'empty-note',
      position: { x: 0, y: 0 },
      content: '',
      color: 'yellow',
      width: 240,
      height: 160,
      snapToNodeId: null,
    });
    expect(usePipelineEditorStore.getState().stickyNotes[0].content).toBe('');
  });

  it('超长便签内容：2000+ 字符正常存储', () => {
    const longContent = 'A'.repeat(5000);
    usePipelineEditorStore.getState().addStickyNote({
      id: 'long-note',
      position: { x: 0, y: 0 },
      content: longContent,
      color: 'yellow',
      width: 240,
      height: 160,
      snapToNodeId: null,
    });
    expect(usePipelineEditorStore.getState().stickyNotes[0].content).toHaveLength(5000);
  });

  it('便签尺寸为负值：store 不做校验（UI 层做 min 限制）', () => {
    usePipelineEditorStore.getState().addStickyNote({
      id: 'neg-size',
      position: { x: 0, y: 0 },
      content: '负尺寸',
      color: 'yellow',
      width: -100,
      height: -50,
      snapToNodeId: null,
    });
    const note = usePipelineEditorStore.getState().stickyNotes[0];
    expect(note.width).toBe(-100);
    expect(note.height).toBe(-50);
  });

  it('连续快速调用 setEditMode：最后一次生效', () => {
    usePipelineEditorStore.getState().setEditMode(true);
    usePipelineEditorStore.getState().setEditMode(false);
    usePipelineEditorStore.getState().setEditMode(true);
    const s = usePipelineEditorStore.getState();
    expect(s.editMode).toBe(true);
    expect(s.nodePanelOpen).toBe(true);
  });

  it('运行中连续调用 setEditMode(true) 多次：始终不生效', () => {
    usePipelineEditorStore.getState().setRunning(true);
    usePipelineEditorStore.getState().setEditMode(true);
    usePipelineEditorStore.getState().setEditMode(true);
    usePipelineEditorStore.getState().setEditMode(true);
    expect(usePipelineEditorStore.getState().editMode).toBe(false);
  });

  it('contextMenu.nodeId 为 null 时（空白区域右键）菜单正常设置', () => {
    usePipelineEditorStore.getState().setContextMenu({ open: true, x: 50, y: 50, nodeId: null });
    expect(usePipelineEditorStore.getState().contextMenu?.nodeId).toBeNull();
  });
});
