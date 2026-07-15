import { create } from 'zustand';

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
}));
