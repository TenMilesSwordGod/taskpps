import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';
import { useReadOnly } from './ReadOnlyContext';

interface EditorPipelineNodeData {
  label?: string;
  executionStrategy?: string;
  maxConcurrentTasks?: number;
  [key: string]: unknown;
}

/**
 * Pipeline 根容器节点 — 淡灰虚线边框
 * 左侧 in 端口（Start 连接入口），右侧 out 端口（连到 End），底部 Post 端口
 *
 * v4 (2026-07 / Bug#45): 新增左侧 in 端口，允许 Start(out)→Pipeline(in) 连接
 */
function EditorPipelineNode({ data, selected }: { data: EditorPipelineNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const label = data.label || 'Pipeline';
  const borderStyle = readOnly ? 'solid' : 'dashed';
  const borderColor = selected ? '#64748b' : '#94a3b8';

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        border: `1.5px ${borderStyle} ${borderColor}`,
        borderRadius: 8,
        background: '#fafbfc',
        position: 'relative',
        boxShadow: selected && !readOnly ? '0 0 0 4px rgba(148,163,184,0.12)' : undefined,
        minWidth: 200,
        minHeight: 200,
      }}
    >
      {/* 注意(2026-07): 只读模式下隐藏所有 Handle */}
      {!readOnly && (
        <>
          {/* v4 (2026-07 / Bug#45): In 端口（入口）— 左侧 */}
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
        </>
      )}

      {/* 标题 */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          left: 12,
          fontFamily: FONT_MONO,
          fontSize: 12,
          fontWeight: 600,
          color: '#64748b',
          letterSpacing: 0.5,
        }}
      >
        {label}
      </div>
    </div>
  );
}

export default memo(EditorPipelineNode);
