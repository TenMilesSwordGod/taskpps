import { create } from 'zustand';

/** 便签颜色类型 */
export type StickyColor = 'yellow' | 'blue' | 'green' | 'pink' | 'orange';

/** 便签 5 色配色方案（N8N 风格） */
export const STICKY_COLORS: Record<StickyColor, { bg: string; border: string; dot: string; label: string }> = {
  yellow: { bg: '#FFF9DB', border: '#FCC419', dot: '#F59F00', label: '黄' },
  blue: { bg: '#E7F5FF', border: '#74C0FC', dot: '#339AF0', label: '蓝' },
  green: { bg: '#EBFBEE', border: '#69DB7C', dot: '#40C057', label: '绿' },
  pink: { bg: '#FFF0F6', border: '#F783AC', dot: '#E64980', label: '粉' },
  orange: { bg: '#FFF4E6', border: '#FFA94D', dot: '#F76707', label: '橙' },
};

/** 便签数据（纯视觉，不参与 Pipeline 数据模型） */
export interface StickyNoteItem {
  id: string;
  position: { x: number; y: number };
  content: string;
  color: StickyColor;
  width: number;
  height: number;
  snapToNodeId?: string | null;
}

/**
 * 流水线编辑器状态 — 管理编辑/只读模式、节点面板、运行态锁定
 *
 * 设计决策：
 * - 编辑模式开启时自动打开节点面板，关闭时收起面板（N8N 风格联动）
 * - 运行中强制只读：isRunning=true 时锁定 editMode=false，禁止任何编辑操作
 * - 面板仅在编辑模式下可 toggle
 */

export interface PipelineEditorState {
  /** 编辑模式 vs 只读模式 */
  editMode: boolean;
  /** 设置编辑模式；运行中切换为编辑模式不生效 */
  setEditMode: (mode: boolean) => void;

  /** 左侧节点面板是否打开 */
  nodePanelOpen: boolean;
  /** 切换面板（仅在编辑模式生效） */
  toggleNodePanel: () => void;
  /** 直接设置面板状态 */
  setNodePanelOpen: (open: boolean) => void;

  /** 流水线是否正在运行 */
  isRunning: boolean;
  /** 设置运行状态；运行时强制只读模式 */
  setRunning: (running: boolean) => void;

  /** 右键菜单状态 */
  contextMenu: {
    open: boolean;
    x: number;
    y: number;
    nodeId: string | null;
  } | null;
  setContextMenu: (menu: PipelineEditorState['contextMenu']) => void;
  closeContextMenu: () => void;

  /** 便签管理（纯视觉元素） */
  stickyNotes: StickyNoteItem[];
  addStickyNote: (note: StickyNoteItem) => void;
  removeStickyNote: (id: string) => void;
  updateStickyNote: (id: string, data: Partial<StickyNoteItem>) => void;
}

export const usePipelineEditorStore = create<PipelineEditorState>((set) => ({
  editMode: false,
  nodePanelOpen: false,
  isRunning: false,

  setEditMode: (mode) =>
    set((s) => {
      // 运行中禁止切换为编辑模式
      if (s.isRunning && mode) return {};
      return {
        editMode: mode,
        // 编辑→开面板，只读→关面板（N8N 联动逻辑）
        nodePanelOpen: mode,
      };
    }),

  toggleNodePanel: () =>
    set((s) => {
      if (!s.editMode) return {};
      return { nodePanelOpen: !s.nodePanelOpen };
    }),

  setNodePanelOpen: (open) => set({ nodePanelOpen: open }),

  setRunning: (running) =>
    set(() => {
      if (running) {
        // 开始运行 → 强制只读 + 关闭面板
        return { isRunning: true, editMode: false, nodePanelOpen: false };
      }
      return { isRunning: false };
    }),

  contextMenu: null,
  setContextMenu: (menu) => set({ contextMenu: menu }),
  closeContextMenu: () => set({ contextMenu: null }),

  /** 便签列表 */
  stickyNotes: [] as StickyNoteItem[],
  addStickyNote: (note) => set((s) => ({ stickyNotes: [...s.stickyNotes, note] })),
  removeStickyNote: (id) => set((s) => ({ stickyNotes: s.stickyNotes.filter((n) => n.id !== id) })),
  updateStickyNote: (id, data) =>
    set((s) => ({
      stickyNotes: s.stickyNotes.map((n) => (n.id === id ? { ...n, ...data } : n)),
    })),
}));
