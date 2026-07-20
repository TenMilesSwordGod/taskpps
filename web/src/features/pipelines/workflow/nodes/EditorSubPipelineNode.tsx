import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';

interface EditorSubPipelineNodeData {
  label?: string;
  executionStrategy?: string;
  maxConcurrentTasks?: number;
  [key: string]: unknown;
}

/**
 * SubPipeline 可编辑容器节点 — n8n 风格
 * 蓝色虚线边框，左 in / 右 out / 底 post 端口，角标显示执行策略
 */
function EditorSubPipelineNode({ data, selected }: { data: EditorSubPipelineNodeData; selected?: boolean }) {
  const label = data.label || 'SubPipeline';
  const strategy = data.executionStrategy || 'sequential';
  const maxParallel = data.maxConcurrentTasks;
  const borderColor = selected ? '#1d4ed8' : '#3b82f6';

  const badgeText = strategy === 'parallel'
    ? `PAR(${maxParallel || '∞'})`
    : 'SEQ';
  const badgeBg = strategy === 'parallel' ? '#fce7f3' : '#e0e7ff';
  const badgeColor = strategy === 'parallel' ? '#be185d' : '#4338ca';

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        border: `3px dashed ${borderColor}`,
        borderRadius: 12,
        background: '#eff6ff',
        position: 'relative',
        boxShadow: selected ? '0 0 0 4px rgba(59,130,246,0.12)' : undefined,
        minWidth: 200,
        minHeight: 120,
      }}
    >
      {/* In 端口 — 左侧 */}
      <Handle
        id="in"
        type="target"
        position={Position.Left}
        style={{
          width: 8,
          height: 8,
          background: 'transparent',
          border: '2px solid #64748b',
          borderRadius: '50%',
          left: -5,
          top: '50%',
        }}
      />

      {/* Out 端口 — 右侧 */}
      <Handle
        id="out"
        type="source"
        position={Position.Right}
        style={{
          width: 8,
          height: 8,
          background: 'transparent',
          border: '2px solid #64748b',
          borderRadius: '50%',
          right: -5,
          top: '50%',
        }}
      />

      {/* Post 端口 — 底部 */}
      <Handle
        id="post"
        type="source"
        position={Position.Bottom}
        style={{
          width: 8,
          height: 8,
          background: 'transparent',
          border: '2px solid #ef4444',
          borderRadius: '50%',
          bottom: -5,
        }}
      />

      {/* 标题栏 */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          left: 12,
          right: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'transparent',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 14, color: '#3b82f6' }}>⬡</span>
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 13,
              fontWeight: 700,
              color: '#1e40af',
            }}
          >
            {label}
          </span>
        </div>
        <span
          style={{
            padding: '1px 6px',
            borderRadius: 4,
            background: badgeBg,
            color: badgeColor,
            fontSize: 10,
            fontFamily: FONT_MONO,
            fontWeight: 600,
          }}
        >
          {badgeText}
        </span>
      </div>
    </div>
  );
}

export default memo(EditorSubPipelineNode);
