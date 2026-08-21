/**
 * DAG 节点共享设计 token —— "黑白极简"（Monochrome）视觉语言
 *
 * 设计理念：CI/CD 工具读起来像一张被照亮的工位 — 中性灰底 + 黑色强调。
 * v3 (2026-07): 曾由「工程蓝图」改造为暖中性灰 + 暖橙 #FF6D5A。
 * v4 (2026-07): 用户反馈橙色刺激，accent 收敛为黑 #1F1F1F，中性色全部去暖化，
 *   仅保留语义状态色（成功/失败/跳过）。
 * - 等宽字体承载所有技术文本（任务名、类型、条件、编号）
 * - 发丝级中性灰边框，无投影
 * - 类型用 6×6 色块标识（电阻色环隐喻）
 * - 状态作为整卡边框色 + 极淡晕染，可扫读
 * - 边作为连续"流轨"，而非装饰性曲线
 */

import type { TaskStatus, TaskType } from '@/types';

/** 节点尺寸常量（与 usePipelineGraph / dagreLayout 共享） */
export const NODE_SIZE = {
  TASK_W: 150,
  TASK_H: 36,
  GATEWAY: 46,
  WHEN: 76,
  POST_H: 26,
  POST_W: 168,
} as const;

/** 画布与结构色
 * v4 (2026-07): canvas 中性暖白 #FAFAFA，accent 由暖橙改为黑 #1F1F1F
 */
export const INK = {
  canvas: '#FAFAFA', // 暖白画布底（DAG 编辑工位）
  card: '#FFFFFF', // 节点填充
  border: '#E0E0E0', // 暖灰发丝边框
  borderHover: '#D4D4D4', // 悬停边框
  borderActive: '#BFBFBF', // 结构边框
  textPrimary: '#262626', // 主文本（暖近黑）
  textSecondary: '#525252', // 次文本
  textMuted: '#8C8C8C', // 弱文本
  accent: '#1F1F1F', // 黑色签名强调色（流/活动/选中）
} as const;

/** 任务状态 → 颜色（边框 / 边）
 * v2 (2026-07): cancelled 从 #EF4444（与 failed 同色造成语义混淆）改为 #8C8C8C，
 *   与 Dashboard/RunList 已有行为对齐，区分"失败(红)"与"取消(灰)"
 * v4 (2026-07): running 状态用黑 #1F1F1F（黑白主题激活态），
 *   pending/cancelled 中性灰 #8C8C8C
 */
export const STATUS_COLOR: Record<TaskStatus, string> = {
  pending: '#8C8C8C',
  running: '#1F1F1F',
  success: '#10B981',
  failed: '#EF4444',
  skipped: '#F59E0B',
  cancelled: '#8C8C8C',
};

/** 任务状态 → 软背景色（用于徽章 / 节点晕染）
 * v2 (2026-07): cancelled soft bg 从 #FEE2E2（红色系）改为 #F2F2F2（灰色系）
 * v4 (2026-07): running soft bg 用浅灰 #F0F0F0（黑白主题）
 */
export const STATUS_SOFT_BG: Record<TaskStatus, string> = {
  pending: '#F2F2F2',
  running: '#F0F0F0',
  success: '#D1FAE5',
  failed: '#FEE2E2',
  skipped: '#FEF3C7',
  cancelled: '#F2F2F2',
};

/** 任务状态 → 短代码（等宽徽章） */
export const STATUS_CODE: Record<TaskStatus, string> = {
  pending: 'PEND',
  running: 'RUN',
  success: 'OK',
  failed: 'FAIL',
  skipped: 'SKIP',
  cancelled: 'CANC',
};

/** 任务类型 → 主色（色环代码） */
export const TYPE_COLOR: Record<TaskType, string> = {
  command: '#10B981',
  invoke: '#6366F1',
  steps: '#8B5CF6',
  plugin: '#EC4899',
  git: '#F59E0B',
  nexus: '#06B6D4',
  ssh: '#64748B',
};

/** 任务类型 → 三字母代码（等宽标签） */
export const TYPE_CODE: Record<TaskType, string> = {
  command: 'CMD',
  invoke: 'INV',
  steps: 'STP',
  plugin: 'PLG',
  git: 'GIT',
  nexus: 'NEX',
  ssh: 'SSH',
};

/** 任务类型 → 中文标签（保留用于 Tooltip） */
export const TYPE_LABEL: Record<TaskType, string> = {
  command: '命令',
  invoke: '调用',
  steps: '步骤',
  plugin: '插件',
  git: 'Git',
  nexus: 'Nexus',
  ssh: 'SSH',
};

/** 任务状态 → 中文标签（保留用于 Tooltip） */
export const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: '待执行',
  running: '执行中',
  success: '成功',
  failed: '失败',
  skipped: '跳过',
  cancelled: '取消',
};

/** 等宽字体栈 */
export const FONT_MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Consolas, "Liberation Mono", Menlo, monospace';
