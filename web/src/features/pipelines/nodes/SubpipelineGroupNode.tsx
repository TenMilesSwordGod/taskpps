import type { NodeProps } from '@xyflow/react';
import { Handle, Position } from '@xyflow/react';
import { INK, FONT_MONO } from './nodeTokens';

interface SubpipelineGroupData extends Record<string, unknown> {
  label: string;
  taskCount: number;
}

/**
 * 子流水线分组容器 —— 工程蓝图风格"规格框"
 * 点状发丝边框，无填充，顶部等宽标签（spec stamp 风格）
 */
export default function SubpipelineGroupNode({ data }: NodeProps) {
  const { label, taskCount } = data as unknown as SubpipelineGroupData;

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        border: `1px dashed ${INK.borderActive}`,
        borderRadius: 6,
        background: 'transparent',
        position: 'relative',
        pointerEvents: 'none',
      }}
    >
      {/* 顶部"规格印章"标签 —— 等宽，覆盖上边框 */}
      <div
        style={{
          position: 'absolute',
          top: -9,
          left: 12,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          background: INK.canvas,
          padding: '0 6px',
          fontFamily: FONT_MONO,
          fontSize: 10,
          fontWeight: 600,
          color: INK.textSecondary,
          letterSpacing: 0.4,
          whiteSpace: 'nowrap',
        }}
      >
        <span>{label}</span>
        <span
          style={{
            color: INK.textMuted,
            fontWeight: 400,
          }}
        >
          / {taskCount}
        </span>
      </div>

      {/* 输入点 —— START / 上游 group 连入（target 类型） */}
      <Handle
        id="top"
        type="target"
        position={Position.Top}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-0 !-top-[3px]"
      />
      {/* 内部出口 —— group → 首 task（source 类型，与 top 同位置） */}
      <Handle
        id="top-out"
        type="source"
        position={Position.Top}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-0 !-top-[3px]"
      />
      {/* 输出点 —— group → __end__ / 下游 group（source 类型） */}
      <Handle
        id="bottom"
        type="source"
        position={Position.Bottom}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-0 !-bottom-[3px]"
      />
      {/* 内部汇聚点 —— 末 task / alt 路径汇入此点（target 类型，与 bottom 同位置） */}
      <Handle
        id="exit"
        type="target"
        position={Position.Bottom}
        className="!w-1.5 !h-1.5 !bg-slate-500 !border-0 !-bottom-[3px]"
      />
    </div>
  );
}
