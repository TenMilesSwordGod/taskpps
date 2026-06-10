import type { NodeProps } from '@xyflow/react';
import { Handle, Position } from '@xyflow/react';

interface SubpipelineGroupData extends Record<string, unknown> {
  label: string;
  taskCount: number;
}

/** 子流水线分组框 —— 渲染为虚线边框的容器 */
export default function SubpipelineGroupNode({ data }: NodeProps) {
  const { label, taskCount } = data as unknown as SubpipelineGroupData;

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        border: '2px dashed #d1d5db',
        borderRadius: 12,
        background: '#f9fafb',
        position: 'relative',
        pointerEvents: 'none',
      }}
    >
      {/* 标签 */}
      <div
        style={{
          position: 'absolute',
          top: -14,
          left: 16,
          background: '#f9fafb',
          padding: '2px 10px',
          borderRadius: 6,
          fontSize: 13,
          fontWeight: 600,
          color: '#374151',
          border: '1px solid #e5e7eb',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
        <span style={{ marginLeft: 6, fontWeight: 400, color: '#9ca3af', fontSize: 11 }}>
          {taskCount} 个任务
        </span>
      </div>

      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden' }} />
      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden' }} />
    </div>
  );
}
