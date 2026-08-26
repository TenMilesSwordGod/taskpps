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
 * 菱形决策节点 —— v11 轻量化
 *
 * 保留菱形（条件分支的通用形状语义，一眼可辨）；配色减噪：
 * 深琥珀描边 + 近白底 → 浅琥珀描边 + 暖白底，摘要文字降为 amber-700
 * （≥4.5:1）。v11 方位随 LR 流向迁移：入 Left、yes 出 Right（顺流）、
 * no 出 Bottom（向下绕行汇入组出口）。
 */
function DecisionNodeComponent({ data }: { data: DecisionNodeData }) {
  const { when } = data;
  const summary = whenSummary(when);
  const SIZE = 64;
  const INNER = 44;

  return (
    <Tooltip
      title={
        <div style={{ fontFamily: FONT_MONO, fontSize: 11, lineHeight: 1.6 }}>
          <span style={{ color: '#4ADE80' }}>✓ yes → run</span>
          <span style={{ color: '#9CA3AF' }}> when: {when}</span>
          <br />
          <span style={{ color: '#9CA3AF' }}>✗ no → skip</span>
        </div>
      }
    >
      <div
        data-testid="decision-node"
        className="relative flex items-center justify-center"
        style={{ width: SIZE, height: SIZE }}
      >
        {/* Target handle — 左侧入边 */}
        <Handle
          type="target"
          position={Position.Left}
          id="target"
          className="!w-1 !h-1 !bg-amber-500 !border-0 !-left-[2px]"
        />

        {/* 菱形 —— 旋转 45° 方块 + CSS 边框（无 clip-path 锯齿问题） */}
        <div
          aria-hidden
          className="absolute"
          style={{
            width: INNER,
            height: INNER,
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%) rotate(45deg)',
            backgroundColor: '#FFFBEB',
            border: '1.5px solid #FCD34D',
            borderRadius: 3,
          }}
        />

        {/* 条件摘要文本（不旋转，覆盖在菱形上）
            v6 (2026-08): inline-block + maxWidth + overflow 约束保留 ——
            长变量名不再横穿菱形轮廓、压住 yes/no 边锚点 */}
        <span
          className="relative z-10 text-center leading-none select-none cursor-default"
          style={{
            fontFamily: FONT_MONO,
            fontSize: 10.5,
            fontWeight: 600,
            color: '#B45309',
            letterSpacing: 0.1,
            display: 'inline-block',
            maxWidth: 48,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {summary}
        </span>

        {/* Yes source handle — 右侧（顺流 → 条件任务） */}
        <Handle
          type="source"
          position={Position.Right}
          id="yes"
          className="!w-1 !h-1 !bg-green-500 !border-0 !-right-[2px]"
        />

        {/* No source handle — 底部（LR 流向下绕行汇入组出口） */}
        <Handle
          type="source"
          position={Position.Bottom}
          id="no"
          className="!w-1 !h-1 !bg-gray-400 !border-0 !-bottom-[2px]"
        />
      </div>
    </Tooltip>
  );
}

export default memo(DecisionNodeComponent);
