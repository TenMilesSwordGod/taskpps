/**
 * DAG 节点共享设计 token
 *
 * 设计理念演进：
 * v3 (2026-07): 由「工程蓝图」改造为暖中性灰 + 暖橙 #FF6D5A。
 * v4 (2026-07): 用户反馈橙色刺激，accent 收敛为黑 #1F1F1F，中性色全部去暖化，
 *   仅保留语义状态色（成功/失败/跳过）——「黑白极简」。
 * v5 (2026-08): 用户反馈黑白主题过于肃穆（"全是黑色太肃穆"），整体迁移到
 *   「n8n 工作流」视觉语言：
 *   - 冷调浅灰画布 + 白色圆角卡片 + 柔和投影（节点从画布上"浮起"）
 *   - 品牌强调色回归 n8n 橙红 #FF6D5A，仅小面积使用（选中描边/运行态），
 *     避免大面积橙色的视觉刺激（v4 的教训）
 *   - 连接线统一柔和灰蓝，降低与节点的对比噪音；语义边（yes/start）保留绿
 *   - running 状态改用蓝色 #3B82F6（业界惯例：蓝=进行中），与 failed 红、
 *     accent 橙拉开距离，避免语义混淆
 *   - 等宽字体承载所有技术文本（任务名、类型、条件、编号）
 *   - 类型用彩色标识条 + 三字母代码标识（延续电阻色环隐喻）
 * v7-v10 (2026-08): 多轮 n8n 化微调（卡片两行布局、端口显隐、边样式工厂）。
 *
 * v11 (2026-08) —— 视觉世界替换：真·n8n workflow canvas 语法
 * ------------------------------------------------------------------
 * THESIS: 一张从左到右流动的 n8n 画布 —— 水平流向、图形语言（glyph 图标
 *         而非文字码）、贝塞尔曲线连线。拒绝"AI 仪表盘"的竖直流程图、
 *         文字徽章与芯片堆砌。
 * OWN-WORLD: 画布 #F6F8FA 细点阵；节点 = 白底 1px #DBDFE7 边 radius 10
 *         紧凑阴影的 n8n 卡片（36px 类型色图标块 + 白色 glyph + sans 名称
 *         + 弱化副标题）；START/END = trigger 式节点卡片（非圆形）；
 *         分组 = 极浅容器（无阴影、sans 标签、无芯片）；状态 = 边框着色
 *         + 右上角圆形徽章；选中 = n8n 橙小面积描边；贝塞尔曲线无箭头。
 * STORY: 用户一眼读出"从左到右的编排流"，节点像 n8n 的应用卡片，
 *         执行状态通过边框与角标一眼可辨。
 * FIRST VIEWPORT: 单行工具栏（面包屑 + 模式切换 + 导出 + 黑色触发运行）
 *         下方全高画布：START 卡最左，任务链水平流动，END 卡最右。
 * FORM: brief-pinned —— 用户指定 n8n 风格（跳过 concept-seed roll）。
 * FINISH: unreviewed and undocumented is unfinished; this build ends with
 *         the finish review, the verdict, and DESIGN.md.
 * ------------------------------------------------------------------
 * 关键反转（相对 v7-v10）：
 * - 流向 TB → LR（dagre rankdir=LR；bezier 在水平流向下才是顺流曲线，
 *   v10 弃用 bezier 的"下垂 S 弯"根因即垂直流向，方向翻转后消除）
 * - 图标块内文字码（CMD/INV）→ 白色 glyph 图标（文字码是 AI 生成感的
 *   最大来源；n8n 用服务品牌 glyph）——mono 退守命令摘要（代码语义）
 * - 状态表达：背景软染 + 左缘色条 → 边框着色 + 右上角徽章
 *   （n8n 执行态语汇；同时消除 craft-floor 禁的 >1px 彩色 border-left）
 * - 组容器：白投影卡 + 芯片行 → 极浅底 + 细边 + sans 弱标签（无芯片）
 * - 连线：smoothstep 直角 + 箭头 → bezier 曲线 + 无箭头（n8n 画布无虚线
 *   无箭头，流向由 LR 布局表达；虚线全部退役）
 */

import type { TaskStatus, TaskType } from '@/types';
import {
  ApartmentOutlined,
  ApiOutlined,
  BranchesOutlined,
  CheckOutlined,
  CloseOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  LinkOutlined,
  LoadingOutlined,
  MinusOutlined,
  PlayCircleFilled,
  StopFilled,
} from '@ant-design/icons';

/** 节点尺寸常量（与 usePipelineGraph / dagreLayout 共享）
 * v11 (2026-08): n8n 卡片比例 —— 任务卡 200×56（36px 图标块 + 两行文本）；
 * START/END 从 40px 圆形改为 trigger 式卡片（图标块 + 文字）
 */
export const NODE_SIZE = {
  TASK_W: 200,
  TASK_H: 56,
  GATEWAY: 46,
  WHEN: 76,
  POST_H: 26,
  POST_W: 168,
  /** START trigger 卡（图标块 + "开始" + "Trigger"） */
  SENTINEL_START_W: 112,
  /** END trigger 卡（图标块 + "结束" + "End"） */
  SENTINEL_END_W: 96,
  SENTINEL_H: 56,
} as const;

/** 画布与结构色
 * v11 (2026-08): 对齐 n8n 画布色板 —— 边框 #DBDFE7、节点标题 #525356、
 * 副标题 #71747A（n8n 节点文字色）；画布底提亮为 #F6F8FA
 */
export const INK = {
  canvas: '#F6F8FA', // n8n 画布浅灰底
  card: '#FFFFFF', // 节点填充
  border: '#DBDFE7', // n8n 节点发丝边框
  borderHover: '#B8C0CC', // 悬停边框
  borderActive: '#94A3B8', // 结构边框
  textPrimary: '#525356', // n8n 节点标题色（比纯黑柔和）
  textSecondary: '#71747A', // n8n 节点副标题色
  textMuted: '#8D939E', // 弱文本（仅用于装饰，正文不用）
  accent: '#FF6D5A', // n8n 品牌橙红 —— 选中/激活的小面积强调色
} as const;

/** 节点卡片投影（n8n：细边框 + 紧凑阴影，二者同用但不做"宽软影+边框"幽灵卡）
 * v11 (2026-08): 阴影收紧 —— 大扩散阴影是"卡片堆砌"感的来源
 */
export const CARD_SHADOW = '0 1px 2px rgba(15, 23, 42, 0.05), 0 1px 3px rgba(15, 23, 42, 0.07)';

/** v8: 悬停/选中时的抬升阴影 */
export const CARD_SHADOW_ELEVATED =
  '0 2px 4px rgba(15, 23, 42, 0.08), 0 4px 10px rgba(15, 23, 42, 0.08)';

/** 连接线（边）共享 token
 * v11 (2026-08): n8n 语汇 —— 全部实线、无箭头（流向由 LR 布局表达）、
 * bezier 曲线（type:'default'）；虚线退役（n8n 画布无虚线）。
 * 层级靠明度：rail 主流轨 > railSoft 派生流（alt/no/post）。
 */
export const EDGE = {
  /** 默认流轨：中性灰实线（n8n edge 灰，微冷调适配 slate 画布） */
  rail: { stroke: '#A8B0BF', strokeWidth: 2 },
  /** 弱化流轨：post / alt / no 路径 */
  railSoft: { stroke: '#C6CCD8', strokeWidth: 1.75 },
  /** START 出边：绿色（入口语义） */
  start: { stroke: '#10B981', strokeWidth: 2 },
  /** END 入边：中性灰 */
  end: { stroke: '#A8B0BF', strokeWidth: 2 },
  /** decision yes 路径：绿色实线 */
  yes: { stroke: '#22C55E', strokeWidth: 2 },
  /** 跨 subpipeline 边：琥珀实线（跨组依赖语义；虚线已退役） */
  cross: { stroke: '#F59E0B', strokeWidth: 2 },
} as const;

/** 任务状态 → 颜色（边框 / 角标 / MiniMap）
 * v2 (2026-07): cancelled 从 #EF4444 改为 #8C8C8C，区分"失败(红)"与"取消(灰)"
 * v5 (2026-08): running 改用蓝色 #3B82F6（蓝=进行中的业界惯例）
 * v6 (2026-08): cancelled 与 pending 双通道区分 —— v11 起双通道 = 边框色
 *   + 边框线型（cancelled 虚线边框，TaskNode 实现）
 */
export const STATUS_COLOR: Record<TaskStatus, string> = {
  pending: '#94A3B8',
  running: '#3B82F6',
  success: '#10B981',
  failed: '#EF4444',
  skipped: '#F59E0B',
  cancelled: '#64748B',
};

/**
 * v11 (2026-08): 状态角标语义 —— n8n 执行态语汇（右上角圆形徽章）。
 * pending 不显示角标（默认态零噪音）；skipped 用减号（语义：未执行），
 * cancelled 用空心（边框虚线 + 灰角标）。
 * 为什么存组件而非字符：craft-floor 禁 Unicode 字符充当图标系统，
 * 角标一律用 @ant-design/icons 真实图标。
 */
export const STATUS_BADGE: Partial<Record<TaskStatus, typeof CheckOutlined>> = {
  running: LoadingOutlined,
  success: CheckOutlined,
  failed: CloseOutlined,
  skipped: MinusOutlined,
  cancelled: MinusOutlined,
};

/** 任务状态 → 角标底色（徽章圆形背景，白色图标） */
export const STATUS_BADGE_BG: Record<TaskStatus, string> = {
  pending: 'transparent',
  running: '#3B82F6',
  success: '#10B981',
  failed: '#EF4444',
  skipped: '#F59E0B',
  cancelled: '#8D939E',
};

/** 任务状态 → 短代码（保留用于 Tooltip 文案） */
export const STATUS_CODE: Record<TaskStatus, string> = {
  pending: 'PEND',
  running: 'RUN',
  success: 'OK',
  failed: 'FAIL',
  skipped: 'SKIP',
  cancelled: 'CANC',
};

/** 任务状态 → 软背景色（画布节点已不再使用；TaskTree 等运行视图仍引用）
 * v11 (2026-08): 画布节点状态改走「边框 + 角标」，软底染色退役于此；
 * token 保留供 runs 视图（TaskTree）等外部消费者使用
 */
export const STATUS_SOFT_BG: Record<TaskStatus, string> = {
  pending: '#F1F5F9',
  running: '#EFF6FF',
  success: '#D1FAE5',
  failed: '#FEE2E2',
  skipped: '#FEF3C7',
  cancelled: '#F1F5F9',
};

/** 任务类型 → 主色（TaskTree 运行视图等外部消费者用；画布节点不再用类型色）
 * v11.1 (2026-08): 画布节点图标块迁移到石墨中性色（用户反馈"绿色很丑"——
 * 全部 CMD 节点的 4 块同款亮绿是丑感主源；v4 教训修复：只有语义色，
 * 类型由 glyph 形状与 Tooltip 承载）。TYPE_COLOR 保留供 runs 侧消费，
 * 但画布 icon block 一律 TYPE_ICON_BG。
 */
export const TYPE_COLOR: Record<TaskType, string> = {
  command: '#10B981',
  invoke: '#6366F1',
  steps: '#8B5CF6',
  plugin: '#EC4899',
  git: '#F59E0B',
  nexus: '#06B6D4',
  ssh: '#64748B',
};

/**
 * 图标块底色 —— 统一石墨中性（白 glyph 对比度 9.6:1）
 * 为什么不是 per-type 彩色（v8 -600 色阶）：同类型流水线（全 CMD）
 * 会渲染成一片同色方块，是"AI 生成感/很丑"的直接来源；
 * 黑白基调（v4 用户锁定）下类型用 glyph 形状区分足够。
 */
export const TYPE_ICON_BG = '#343A43';

/**
 * 任务类型 → glyph 图标（n8n 语汇：图标块内是图形，不是文字码）
 * v11 (2026-08): 文字码（CMD/INV/STP…）是"AI 生成感"的最大单一来源 ——
 * n8n 的图标块永远是服务品牌 glyph。选型原则：一眼映射任务语义
 * （command=代码、steps=层级、plugin=插头、invoke=链接、git=分支、
 * nexus=数据库、ssh=云服务器）。
 */
export const TYPE_ICON: Record<TaskType, typeof CodeOutlined> = {
  command: CodeOutlined,
  steps: ApartmentOutlined,
  plugin: ApiOutlined,
  invoke: LinkOutlined,
  git: BranchesOutlined,
  nexus: DatabaseOutlined,
  ssh: CloudServerOutlined,
};

/** START/END 哨兵 glyph（trigger 卡图标块内使用） */
export const SENTINEL_ICON = {
  start: PlayCircleFilled,
  end: StopFilled,
} as const;

/**
 * 任务类型 → 深色文字变体（小字号文本专用，≥4.5:1）
 * v11: 保留 —— 类型色文字（如 when 徽章）仍需达标
 */
export const TYPE_INK: Record<TaskType, string> = {
  command: '#047857', // emerald-700，5.5:1
  invoke: '#4338CA', // indigo-700，7.6:1
  steps: '#6D28D9', // violet-700，7.0:1
  plugin: '#BE185D', // pink-700，6.4:1
  git: '#B45309', // amber-700，4.8:1
  nexus: '#0E7490', // cyan-700，5.0:1
  ssh: '#475569', // slate-600，7.0:1
};

/** 任务类型 → 中文标签（图标块的 aria-label，屏幕可读性替代文字码） */
export const TYPE_LABEL: Record<TaskType, string> = {
  command: '命令',
  invoke: '调用',
  steps: '步骤',
  plugin: '插件',
  git: 'Git',
  nexus: 'Nexus',
  ssh: 'SSH',
};

/** 任务状态 → 中文标签（Tooltip 用） */
export const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: '待执行',
  running: '执行中',
  success: '成功',
  failed: '失败',
  skipped: '跳过',
  cancelled: '取消',
};

/**
 * 等宽字体栈 —— v11 起职责收窄：仅命令摘要/条件表达式等"代码语义"文本。
 * 组名、节点名、徽章、图例一律 sans（mono 当"技术感"装饰是 AI 味来源）。
 */
export const FONT_MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Consolas, "Liberation Mono", Menlo, monospace';

/** UI 无衬线字体栈（节点标题/组名/图例） */
export const FONT_SANS = '-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif';
