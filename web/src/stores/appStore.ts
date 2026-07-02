import { create } from 'zustand';

interface AppState {
  /** 当前选中的节点 ID */
  selectedNodeId: string | null;
  setSelectedNodeId: (id: string | null) => void;

  /** 右侧面板宽度 */
  panelWidth: number;
  setPanelWidth: (width: number) => void;

  /** 面板是否最大化 */
  panelMaximized: boolean;
  setPanelMaximized: (maximized: boolean) => void;

  /** 面板是否最小化 */
  panelMinimized: boolean;
  setPanelMinimized: (minimized: boolean) => void;

  /** Help 面板是否最小化 */
  helpPanelMinimized: boolean;
  toggleHelpPanel: () => void;

  /** 是否可编辑（V1 固定为 false） */
  editable: false;
}

export const useAppStore = create<AppState>((set) => ({
  selectedNodeId: null,
  setSelectedNodeId: (id) => set({ selectedNodeId: id }),

  panelWidth: 420,
  setPanelWidth: (width) => set({ panelWidth: width }),

  panelMaximized: false,
  setPanelMaximized: (maximized) => set({ panelMaximized: maximized }),

  panelMinimized: false,
  setPanelMinimized: (minimized) => set({ panelMinimized: minimized }),

  helpPanelMinimized: true,
  toggleHelpPanel: () => set((s) => ({ helpPanelMinimized: !s.helpPanelMinimized })),

  editable: false,
}));
