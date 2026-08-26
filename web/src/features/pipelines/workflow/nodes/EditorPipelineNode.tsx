import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { FONT_SANS, INK } from '@/features/pipelines/nodes/nodeTokens';
import { useReadOnly } from './ReadOnlyContext';

interface EditorPipelineNodeData {
  label?: string;
  executionStrategy?: string;
  maxConcurrentTasks?: number;
  [key: string]: unknown;
}

/**
 * Pipeline 根容器节点
 *
 * v9 (2026-08): 虚线退役，改为发丝实线 + 近白底；悬停加深走 CSS 变量。
 * v11 (2026-08): 随 LR 流向迁移端口 —— in=Left（START 从左连入）、
 * out=Right（连到 END）、post=Bottom（Post 容器挂下方）；
 * 标题从 mono 大写改为 sans 弱标签（与分组容器同语汇）。
 * 保留 handle id 契约（in/out/post）。
 */
function EditorPipelineNode({ data, selected }: { data: EditorPipelineNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const label = data.label || 'Pipeline';
  const borderColor = selected ? '#64748B' : 'var(--wf-card-border, #E4E9F0)';

  return (
    <div
      className="wf-card"
      style={{
        width: '100%',
        height: '100%',
        border: `1px solid ${borderColor}`,
        borderRadius: 14,
        background: 'rgba(251, 252, 254, 0.6)',
        position: 'relative',
        boxShadow: selected && !readOnly ? '0 0 0 2px rgba(100,116,139,0.18)' : undefined,
        minWidth: 200,
        minHeight: 200,
      }}
    >
      {/* 注意(2026-07): 只读模式下隐藏所有 Handle */}
      {!readOnly && (
        <>
          {/* v11 (LR): In 端口 — 左缘（START 从左连入） */}
          <Handle
            id="in"
            type="target"
            position={Position.Left}
            style={{
              width: 10,
              height: 10,
              background: '#FFFFFF',
              border: '2px solid #64748b',
              borderRadius: '50%',
              left: -6,
              top: '50%',
            }}
          />

          {/* v11 (LR): Out 端口 — 右缘（连到 END） */}
          <Handle
            id="out"
            type="source"
            position={Position.Right}
            style={{
              width: 10,
              height: 10,
              background: '#FFFFFF',
              border: '2px solid #64748b',
              borderRadius: '50%',
              right: -6,
              top: '50%',
            }}
          />

          {/* Post 端口 — v11: 底部（Post 容器挂在根容器下方） */}
          <Handle
            id="post"
            type="source"
            position={Position.Bottom}
            style={{
              width: 10,
              height: 10,
              background: '#FFFFFF',
              border: '2px solid #ef4444',
              borderRadius: '50%',
              bottom: -6,
              left: '50%',
            }}
          />
        </>
      )}

      {/* 标题：sans 弱标签（与分组容器头部同语汇） */}
      <div
        style={{
          position: 'absolute',
          top: 10,
          left: 14,
          fontFamily: FONT_SANS,
          fontSize: 12,
          fontWeight: 600,
          color: INK.textMuted,
          letterSpacing: 0.2,
        }}
      >
        {label}
      </div>
    </div>
  );
}

export default memo(EditorPipelineNode);
