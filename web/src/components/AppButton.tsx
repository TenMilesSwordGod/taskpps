import { Button } from 'antd';
import type { ButtonProps } from 'antd';
import { isValidElement, type ComponentType, type ReactNode } from 'react';

/**
 * 通用按钮 AppButton —— 把项目既有按钮约定收敛到一处。
 *
 * 设计决策（为什么这么写）：
 * - 全站按钮绝大多数是 `size="small"`，散落在各调用点的默认值容易漏写导致高度不一致，
 *   因此在组件内统一默认 small，需要更大尺寸时显式覆盖 size；
 * - 项目里 lucide-react 图标固定 `size={14}`，逐处手写既重复又容易漂移，
 *   故 icon 支持「已实例化节点」与「组件」两种形态，后者统一按 14px 渲染；
 * - 「刷新中图标转圈」（RefreshCw/Radar + animate-spin）在项目里重复出现多次，
 *   故提供 iconClassName 透传 className，避免为加一个动画类就退回手写节点；
 * - 旧代码里还有 @ant-design/icons（如 <PlusOutlined />）与需要自定义尺寸的场景，
 *   因此已实例化的 ReactNode 一律原样透传、不做尺寸与 className 改写，保证向后兼容。
 */

/** 语义化外观：调用点表达「这是什么操作」，而不是「AntD type 填什么」 */
export type AppButtonVariant = 'primary' | 'secondary' | 'danger' | 'text' | 'link' | 'dashed';

/** 兼容 lucide-react 这类「组件式图标」：只声明我们实际会透传的 props */
type IconComponent = ComponentType<{ size?: number | string; className?: string }>;

/**
 * 注意(2026-09)：AntD 5.21+ 自身也有 variant/color 两个 props（描述 outlined/solid 轴），
 * 与本组件的语义 variant 不是同一概念。这里显式 Omit 掉，避免同名冲突与调用点误解；
 * 项目现状统一走 type + danger 这套语义，本组件沿用之。
 */
export interface AppButtonProps extends Omit<ButtonProps, 'type' | 'icon' | 'variant' | 'color'> {
  /** 语义化外观；未指定时按 AntD 原生 type/danger 透传 */
  variant?: AppButtonVariant;
  /** 仍允许直接传 AntD 原生 type，兼容未使用 variant 的既有写法 */
  type?: ButtonProps['type'];
  /** 已实例化的图标节点原样透传；传组件（如 lucide 的 Play）时按 iconSize 渲染 */
  icon?: ReactNode | IconComponent;
  /** 组件式图标的尺寸，默认 14（项目设计规范） */
  iconSize?: number;
  /** 组件式图标的 className（如刷新中的 animate-spin）；元素式图标请直接写在节点上 */
  iconClassName?: string;
}

/** variant → AntD props 的映射表：后续视觉调整只需改这一处 */
const VARIANT_PROPS: Record<AppButtonVariant, Pick<ButtonProps, 'type' | 'danger'>> = {
  primary: { type: 'primary' },
  secondary: { type: 'default' },
  // 破坏性操作默认用「红描边」而非「红色实心」：实心红视觉权重过高，容易误导误点
  danger: { type: 'default', danger: true },
  text: { type: 'text' },
  link: { type: 'link' },
  dashed: { type: 'dashed' },
};

const DEFAULT_ICON_SIZE = 14;

/** 把 icon 归一成 ReactNode：组件式图标补上尺寸/类名，元素式图标保持原样 */
function resolveIcon(
  icon: AppButtonProps['icon'],
  size: number,
  className?: string,
): ReactNode {
  if (icon == null) return undefined;
  if (isValidElement(icon)) return icon;
  const Icon = icon as IconComponent;
  return <Icon size={size} className={className} />;
}

export default function AppButton({
  variant,
  type,
  danger,
  size = 'small',
  icon,
  iconSize = DEFAULT_ICON_SIZE,
  iconClassName,
  ...rest
}: AppButtonProps) {
  const preset = variant ? VARIANT_PROPS[variant] : undefined;

  return (
    <Button
      {...rest}
      size={size}
      // variant 优先于原生 type/danger；未用 variant 时保持 AntD 原有语义
      type={preset?.type ?? type}
      danger={preset?.danger ?? danger}
      icon={resolveIcon(icon, iconSize, iconClassName)}
    />
  );
}
