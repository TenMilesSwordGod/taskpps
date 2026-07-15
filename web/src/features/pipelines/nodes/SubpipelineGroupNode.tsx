import type { NodeProps } from '@xyflow/react';
import { Handle, Position } from '@xyflow/react';
import { INK, FONT_MONO } from './nodeTokens';

interface SubpipelineGroupData extends Record<string, unknown> {
  label: string;
  taskCount: number;
  /** 运行态进度 { done: number, total: number } — v2 (2026-07) */
  runProgress?: { done: number; total: number };
}

/**
 * 子流水线分组容器 —— 工程蓝图风格"规格框"
 * 点状发丝边框，无填充，顶部等宽标签（spec stamp 风格）
 * v2 (2026-07): 添加运行态进度指示
 */
export default function SubpipelineGroupNode({ data }: NodeProps) {
  const { label, taskCount, runProgress } = data as unknown as SubpipelineGroupData;

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
      {/* v2 (2026-07): 运行中进度条（容器 header 下方 3px 细线） */}
      {runProgress && runProgress.total > 0 && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: 3,
            backgroundColor: '#E9ECEF',
            borderRadius: '6px 6px 0 0',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${Math.round((runProgress.done / runProgress.total) * 100)}%`,
              backgroundColor: '#4C6EF5',
              borderRadius: '6px 0 0 0',
              transition: 'width 300ms ease',
            }}
          />
        </div>
      )}

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
        {runProgress ? (
          <span
            style={{
              color: '#4C6EF5',
              fontWeight: 600,
            }}
          >
            {runProgress.done}/{runProgress.total}
          </span>
        ) : (
          <span
            style={{
              color: INK.textMuted,
              fontWeight: 400,
            }}
          >
            / {taskCount}
          </span>
        )}
      </div>

      {/* 输入点 —— START / 上游 group 连入（target 类型，Position.Top 边从上方进入） */}
      <Handle
        id="top"
        type="target"
        position={Position.Top}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-0 !-top-[3px]"
        style={{ left: '25%' }}
      />
      {/* 内部出口 —— group → 首 task（source 类型，Position.Top 使边从顶部向下路由到子节点） */}
      <Handle
        id="top-out"
        type="source"
        position={Position.Top}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-0 !-top-[3px]"
        style={{ left: '75%' }}
      />
      {/* 输出点 —— group → __end__ / 下游 group（source 类型） */}
      <Handle
        id="bottom"
        type="source"
        position={Position.Bottom}
        className="!w-1.5 !h-1.5 !bg-slate-400 !border-0 !-bottom-[3px]"
        style={{ left: '25%' }}
      />
      {/* 内部汇聚点 —— 末 task / alt/no 路径汇入此点（target 类型，Position.Bottom 使边从上方子节点向下汇入底部） */}
      <Handle
        id="exit"
        type="target"
        position={Position.Bottom}
        className="!w-1.5 !h-1.5 !bg-slate-500 !border-0 !-bottom-[3px]"
        style={{ left: '75%' }}
      />
    </div>
  );
}
