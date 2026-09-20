import type { ReactNode, SVGProps } from 'react';

/**
 * 品牌图标库（Engineering Schematic 工程蓝图风格）
 *
 * 设计约定（为什么这么写）：
 * - 统一 viewBox="0 0 24 24" + width/height="1em"：图标随父级 font-size 缩放，
 *   菜单（14px）、按钮（14px）、树节点（13px）可直接复用，无需逐个传尺寸。
 * - stroke="currentColor" + fill="none"：颜色完全由父级 color/style 透传，
 *   便于跟随 AntD token 与 nodeTokens 状态色，不在图标内写死颜色。
 * - strokeWidth=2 + 圆角端点：与既有 workflow/icons 节点图标、lucide-react 保持
 *   同一视觉语言，避免自绘图标与第三方图标混用时出现粗细/端点不一致。
 * - 默认 aria-hidden="true"：图标是装饰性元素，语义由相邻文本或按钮提供；
 *   需要独立语义时由调用方显式传 aria-label 覆盖。
 * - verticalAlign: -0.125em（对齐 lucide 默认值）：图标内联在文本中时与基线对齐，
 *   避免 SVG 默认 baseline 造成的下沉 1-2px。
 */
function StrokeIcon({ children, style, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ verticalAlign: '-0.125em', ...style }}
      {...props}
    >
      {children}
    </svg>
  );
}

export type IconProps = SVGProps<SVGSVGElement>;

/**
 * 仪表盘图标（P0 导航）
 * 设计：半圆仪表盘 + 指针 + 轴心点，比通用"四方块"更贴合本项目"运行状态总览"的语义。
 */
export function DashboardIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <path d="M4 14a8 8 0 0 1 16 0" />
      <path d="M12 14l3.5-4.5" />
      <circle cx="12" cy="14" r="1.3" fill="currentColor" stroke="none" />
    </StrokeIcon>
  );
}

/**
 * 流水线图标（P0 导航 / 运行树根节点）
 * 设计：一入二出的 DAG 分叉（源节点 → 并行任务），直接映射本产品"任务编排"的领域语义，
 * 替代 AntD PartitionOutlined（表达的是"分区"，与流水线无关）。
 */
export function PipelineIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <circle cx="5.5" cy="12" r="2.5" />
      <circle cx="18.5" cy="6" r="2.5" />
      <circle cx="18.5" cy="18" r="2.5" />
      <path d="M7.8 11l8.4-4" />
      <path d="M7.8 13l8.4 4" />
    </StrokeIcon>
  );
}

/**
 * 运行历史图标（P0 导航）
 * 设计：逆时针回卷箭头 + 时钟指针，表达"可回溯的运行记录"；
 * 箭头方向与缺口位置经过调整，避免与 AntD 的普通圆钟图标混淆。
 */
export function RunHistoryIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <path d="M12 4a8 8 0 1 0 8 8" />
      <path d="M14.5 1.8L12 4l2.5 2.2" />
      <path d="M12 8v4l3 2" />
    </StrokeIcon>
  );
}

/**
 * 服务器图标（P0 导航）
 * 设计：双机架单元 + 指示灯点，与 public/static/servers/*.svg 的机架视觉呼应，
 * 替代通用云朵图标（本项目是自托管 Agent，不是云服务）。
 */
export function ServerIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <rect x="3" y="4" width="18" height="6" rx="1.5" />
      <rect x="3" y="14" width="18" height="6" rx="1.5" />
      <circle cx="7" cy="7" r="1" fill="currentColor" stroke="none" />
      <circle cx="7" cy="17" r="1" fill="currentColor" stroke="none" />
    </StrokeIcon>
  );
}

/**
 * 插件图标（P0 导航 / 节点面板）
 * v2 (2026-09): 从 workflow/icons 迁移到品牌图标库，导航与节点面板共用同一份路径，
 *   消除"同一概念两套图标"的不一致。
 */
export function PluginIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <path d="M4 11a2 2 0 0 1 2-2h1V6.5a2.5 2.5 0 0 1 5 0V9h4a2 2 0 0 1 2 2v1.5a2.5 2.5 0 0 1 0 5V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
    </StrokeIcon>
  );
}

/**
 * 子流水线图标（节点面板 / 运行树 / 属性面板）
 * v2 (2026-09): 从 workflow/icons 迁移到品牌图标库，统一单一来源。
 */
export function SubPipelineIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <rect x="3" y="3" width="18" height="18" rx="3" strokeDasharray="4 3" />
      <rect x="7" y="7" width="10" height="10" rx="2" />
      <line x1="12" y1="7" x2="12" y2="17" />
      <line x1="7" y1="12" x2="17" y2="12" />
    </StrokeIcon>
  );
}

/**
 * 环境变量图标（属性面板 Env tab）
 * 设计：一对花括号 { }，表达"变量插值"语义；比终端/钥匙图标更贴近 YAML 配置场景。
 */
export function EnvironmentIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <path d="M9.5 4c-2.5 0-2.5 2-2.5 3.5 0 2-.5 3.5-2.5 4.5 2 1 2.5 2.5 2.5 4.5 0 1.5 0 3.5 2.5 3.5" />
      <path d="M14.5 4c2.5 0 2.5 2 2.5 3.5 0 2 .5 3.5 2.5 4.5-2 1-2.5 2.5-2.5 4.5 0 1.5 0 3.5-2.5 3.5" />
    </StrokeIcon>
  );
}

/**
 * 依赖图标（属性面板依赖 tab）
 * 设计：git-branch 式分叉（主干 + 分支节点），是 DAG/CI 语境下表达"依赖"的通用图形；
 * 不用链条图标是为了与既有 InvokeIcon（链接）区分。
 */
export function DependencyIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <circle cx="7" cy="5" r="2.5" />
      <circle cx="7" cy="19" r="2.5" />
      <circle cx="17" cy="5" r="2.5" />
      <path d="M7 7.5v9" />
      <path d="M17 7.5A8.5 8.5 0 0 1 8.5 17" />
    </StrokeIcon>
  );
}

/**
 * 设置图标（属性面板高级 tab）
 * 设计：三组滑杆 + 旋钮，表达"可调参数"而非齿轮（齿轮在小尺寸下容易糊成一团）。
 */
export function SettingsIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <path d="M3 6h11.5" />
      <path d="M19.5 6h1.5" />
      <circle cx="17" cy="6" r="2.5" />
      <path d="M3 12h2.5" />
      <path d="M10.5 12h10.5" />
      <circle cx="8" cy="12" r="2.5" />
      <path d="M3 18h10.5" />
      <path d="M18.5 18h2.5" />
      <circle cx="16" cy="18" r="2.5" />
    </StrokeIcon>
  );
}

/** 基本信息图标（属性面板基本 tab）：圆 + i，信息语义的通用图形 */
export function InfoIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 7.5h.01" />
    </StrokeIcon>
  );
}

/** 源码图标（属性面板源码 tab / YAML 切换）：</> 尖括号 + 斜杠 */
export function CodeIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <polyline points="9 7 4 12 9 17" />
      <polyline points="15 7 20 12 15 17" />
      <line x1="13.5" y1="5" x2="10.5" y2="19" />
    </StrokeIcon>
  );
}

/** 帮助图标（帮助面板）：圆 + 问号，替代 AntD QuestionCircleOutlined */
export function HelpIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.2 9.2a2.8 2.8 0 0 1 5.5.9c0 1.9-2.7 2.4-2.7 4" />
      <path d="M12 17.2h.01" />
    </StrokeIcon>
  );
}

/**
 * 示例/模板图标（帮助面板"示例 Pipeline"）
 * 设计：三层堆叠（layers），表达"可复用的模板集合"；比列表图标更不易与运行树混淆。
 */
export function ExamplesIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <polygon points="12 3 21 7.5 12 12 3 7.5" />
      <polyline points="3 12 12 16.5 21 12" />
      <polyline points="3 16.5 12 21 21 16.5" />
    </StrokeIcon>
  );
}

/**
 * 自动布局图标（工作流工具栏"布局"）
 * 设计：层级树（父节点 + 总线 + 两个子节点），表达 dagre 的自动排布结果；
 * 替代 AntD ApartmentOutlined，避免与运行树中的组织架构图形语义混淆。
 */
export function AutoLayoutIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <rect x="9" y="3" width="6" height="5" rx="1.5" />
      <path d="M12 8v6" />
      <path d="M6 14h12" />
      <path d="M6 14v2" />
      <path d="M18 14v2" />
      <rect x="3" y="16" width="6" height="5" rx="1.5" />
      <rect x="15" y="16" width="6" height="5" rx="1.5" />
    </StrokeIcon>
  );
}

/**
 * 导出图片图标（工作流工具栏"导出"）
 * 设计：相框 + 山景 + 下载箭头，同时表达"图片"与"导出"两个动作；
 * 替代相机图标（相机偏"截图"，导出实际是生成 PNG/SVG）。
 */
export function ExportImageIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="3 16 7.5 11.5 11.5 15.5" />
      <path d="M17 13v6" />
      <polyline points="14.5 16.5 17 19 19.5 16.5" />
    </StrokeIcon>
  );
}

/**
 * 结果页图标（运行树"结果页"）
 * 设计：剪贴板 + 对勾，表示"运行产出的结果汇总"；
 * 与 TaskIcon（虚线容器 + 勾）区分：实线文档强调产出物。
 */
export function ResultIcon(props: IconProps) {
  return (
    <StrokeIcon {...props}>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <rect x="9" y="2.5" width="6" height="3" rx="1" />
      <path d="M9 13l2 2 4-4" />
    </StrokeIcon>
  );
}
