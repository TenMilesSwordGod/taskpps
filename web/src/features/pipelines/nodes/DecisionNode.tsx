import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Tooltip } from 'antd';
import { FONT_MONO } from './nodeTokens';

/** 从 when 表达式提取短摘要 */
function whenSummary(expr: string): string {
  const matches = expr.match(/\$\{([^}]+)\}/g);
  if (!matches || matches.length === 0) return expr.length > 10 ? expr.slice(0, 8) + '…' : expr;
  const last = matches[matches.length - 1].slice(2, -1);
  return last.replace(/^(env|params|variables)\./, '');
}

interface DecisionNodeData {
  when: string;
  [key: string]: unknown;
}

/**
 * 菱形决策节点（draw.io / BPMN 风格）
 * - 1 个 target handle（顶部）
 * - 2 个 source handle：right=yes（执行），left=no（跳过）
 * - 菱形内部显示条件摘要
 * - 悬停显示完整条件
 */
function DecisionNodeComponent({ data }: { data: DecisionNodeData }) {
  const { when } = data;
  const summary = whenSummary(when);

  return (
    <Tooltip
      title={
        <div style={{ fontFamily: FONT_MONO, fontSize: 11, lineHeight: 1.6 }}>
          <span style={{ color: '#16A34A' }}>✓ yes → run</span>
          <span style={{ color: '#9CA3AF' }}> when: {when}</span>
          <br />
          <span style={{ color: '#9CA3AF' }}>✗ no → skip</span>
        </div>
      }
    >
      <div
        data-testid="decision-node"
        className="relative flex items-center justify-center"
        style={{ width: 60, height: 60 }}
      >
        {/* Target handle — 顶部入边 */}
        <Handle
          type="target"
          position={Position.Top}
          id="target"
          className="!w-1 !h-1 !bg-amber-500 !border-0 !-top-[2px]"
        />

        {/* 菱形 —— 旋转 45° 方块 + CSS 边框（无 clip-path 锯齿问题） */}
        <div
          aria-hidden
          className="absolute"
          style={{
            width: 40,
            height: 40,
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%) rotate(45deg)',
            backgroundColor: '#FFF7ED',
            border: '1.5px solid #FDBA74',
            borderRadius: 2,
          }}
        />

        {/* 条件摘要文本（不旋转，覆盖在菱形上） */}
        <span
          className="relative z-10 text-center leading-none select-none cursor-default"
          style={{
            fontFamily: FONT_MONO,
            fontSize: 9,
            fontWeight: 600,
            color: '#C2410C',
            letterSpacing: 0.1,
          }}
        >
          {summary}
        </span>

        {/* Yes source handle — 右侧（→ 条件任务） */}
        <Handle
          type="source"
          position={Position.Right}
          id="yes"
          className="!w-1 !h-1 !bg-green-500 !border-0 !right-[-2px]"
        />

        {/* No source handle — 左侧（→ 跳过/绕行） */}
        <Handle
          type="source"
          position={Position.Left}
          id="no"
          className="!w-1 !h-1 !bg-gray-400 !border-0 !left-[-2px]"
        />
      </div>
    </Tooltip>
  );
}

export default memo(DecisionNodeComponent);
