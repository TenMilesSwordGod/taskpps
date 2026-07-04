import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Tooltip } from 'antd';
import { X } from 'lucide-react';
import { NODE_SIZE, FONT_MONO } from './nodeTokens';

interface WhenTargetInfo {
  targetId: string;
  when: string;
}

interface WhenNodeData {
  isGateway?: boolean;
  when?: string;
  whenTargets?: WhenTargetInfo[];
  sourceTaskName?: string;
  targetTaskName?: string;
}

const MAX_SUMMARY_LEN = 8;

/** 琥珀描边色 */
const AMBER_STROKE = '#F59E0B';
/** 琥珀强调色（图标/文字，比描边略深以保证白底对比度） */
const AMBER_INK = '#D97706';
/** 极浅琥珀底色 —— 标识"条件"语义，又不喧宾夺主 */
const AMBER_WASH = '#FFFBEB';

function summarizeWhen(when: string): string {
  const match = when.match(/\$\{([^}]+)\}/);
  if (match) return `\${${match[1]}}`;
  return when.length > MAX_SUMMARY_LEN ? `${when.slice(0, MAX_SUMMARY_LEN)}…` : when;
}

/**
 * 干净的菱形：旋转方块 + 真实 CSS 边框。
 * 用 transform: rotate(45deg) 取代 clip-path —— clip-path 会裁掉自身的 border，
 * 导致描边断裂/锯齿；旋转方块能渲染出完整锐利的菱形描边。
 * 内容作为兄弟节点（不旋转）覆盖在菱形之上。
 */
function Diamond({ size, borderWidth = 1.5 }: { size: number; borderWidth?: number }) {
  return (
    <div
      aria-hidden
      className="absolute"
      style={{
        width: size,
        height: size,
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%) rotate(45deg)',
        backgroundColor: AMBER_WASH,
        border: `${borderWidth}px solid ${AMBER_STROKE}`,
        borderRadius: 1.5,
      }}
    />
  );
}

/**
 * Gateway 节点 —— 排他网关（BPMN 语义：菱形 + X）
 * 浅琥珀底 + 琥珀描边菱形，中心琥珀色 X。
 */
function GatewayNode() {
  const size = NODE_SIZE.GATEWAY; // 46
  const diamondVis = 38;
  return (
    <div
      data-testid="gateway-node"
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
      title="Gateway"
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-1 !h-1 !bg-amber-500 !border-0 !-top-[2px]"
      />
      <Diamond size={diamondVis} />
      <X size={13} strokeWidth={2.6} className="relative z-10" color={AMBER_INK} />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-1 !h-1 !bg-amber-500 !border-0 !-bottom-[2px]"
      />
    </div>
  );
}

/**
 * 普通条件节点 —— 显示 when 表达式摘要
 * 浅琥珀底 + 琥珀描边菱形，等宽摘要文本。
 */
function WhenNodeComponent(props: NodeProps) {
  const { isGateway, when, sourceTaskName, targetTaskName } = (props.data ?? {}) as unknown as WhenNodeData;

  if (isGateway) {
    return <GatewayNode />;
  }

  const summary = when ? summarizeWhen(when) : '';
  const size = NODE_SIZE.WHEN; // 76
  const diamondVis = 62;

  return (
    <div
      data-testid="when-node"
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
      title={`${sourceTaskName ?? ''} → ${targetTaskName ?? ''}`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-1 !h-1 !bg-amber-500 !border-0 !-top-[2px]"
      />
      <Diamond size={diamondVis} />
      <Tooltip title={when}>
        <span
          data-testid="when-node-text"
          className="relative z-10 text-xs font-mono font-medium truncate max-w-[40px] text-center leading-tight cursor-default select-none"
          style={{ fontFamily: FONT_MONO, fontSize: 11, letterSpacing: -0.1, color: AMBER_INK }}
        >
          {summary}
        </span>
      </Tooltip>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-1 !h-1 !bg-amber-500 !border-0 !-bottom-[2px]"
      />
    </div>
  );
}

export default memo(WhenNodeComponent);
