/**
 * DAG 节点共享设计 token —— "工程蓝图"（Engineering Schematic）视觉语言
 *
 * 设计理念：CI/CD 工具应当读起来像工程图纸，而非消费级 App。
 * - 等宽字体承载所有技术文本（任务名、类型、条件、编号）
 * - 发丝级边框（1px slate-200），无投影
 * - 类型用 6×6 色块标识（电阻色环隐喻）
 * - 状态作为 3px 左侧强调条，可扫读
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

/** 画布与结构色 */
export const INK = {
  canvas: '#F8FAFC', // slate-50 画布底
  card: '#FFFFFF', // 节点填充
  border: '#E2E8F0', // slate-200 发丝边框
  borderHover: '#CBD5E1', // slate-300 悬停边框
  borderActive: '#94A3B8', // slate-400 结构边框
  textPrimary: '#0F172A', // slate-900 主文本
  textSecondary: '#475569', // slate-600 次文本
  textMuted: '#94A3B8', // slate-400 弱文本
  accent: '#0EA5E9', // sky-500 签名强调色（流/活动）
} as const;

/** 任务状态 → 颜色（强调条 / 边） */
export const STATUS_COLOR: Record<TaskStatus, string> = {
  pending: '#94A3B8',
  running: '#0EA5E9',
  success: '#10B981',
  failed: '#EF4444',
  skipped: '#F59E0B',
  cancelled: '#EF4444',
};

/** 任务状态 → 软背景色（用于徽章） */
export const STATUS_SOFT_BG: Record<TaskStatus, string> = {
  pending: '#F1F5F9',
  running: '#E0F2FE',
  success: '#D1FAE5',
  failed: '#FEE2E2',
  skipped: '#FEF3C7',
  cancelled: '#FEE2E2',
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
