import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { INK, FONT_MONO } from './nodeTokens';

interface StartEndNodeData {
  variant: 'start' | 'end';
  [key: string]: unknown;
}

/**
 * Start / End 哨兵节点 —— 工程蓝图风格极简胶囊
 * 等宽标签 + 状态色圆点，无投影
 */
function StartEndNodeComponent({ data }: { data: StartEndNodeData }) {
  const isStart = data.variant === 'start';
  const dotColor = isStart ? '#10B981' : '#94A3B8';

  return (
    <>
      {!isStart && (
        <Handle
          type="target"
          position={Position.Top}
          className="!w-1 !h-1 !bg-slate-300 !border-0 !-top-[2px]"
        />
      )}

      <div
        className="flex items-center gap-1.5 bg-white select-none whitespace-nowrap"
        style={{
          padding: '3px 10px 3px 8px',
          border: `1px solid ${INK.border}`,
          borderRadius: 999,
          fontFamily: FONT_MONO,
          fontSize: 10,
          fontWeight: 600,
          color: INK.textSecondary,
          letterSpacing: 0.8,
        }}
      >
        {/* 状态色圆点（实心） */}
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: 999,
            backgroundColor: dotColor,
            flexShrink: 0,
          }}
        />
        <span>{isStart ? 'START' : 'END'}</span>
      </div>

      {isStart && (
        <Handle
          type="source"
          position={Position.Bottom}
          className="!w-1 !h-1 !bg-slate-300 !border-0 !-bottom-[2px]"
        />
      )}
    </>
  );
}

export const StartNode = memo((props: { data: StartEndNodeData }) => (
  <StartEndNodeComponent {...props} />
));
export const EndNode = memo((props: { data: StartEndNodeData }) => (
  <StartEndNodeComponent {...props} />
));
