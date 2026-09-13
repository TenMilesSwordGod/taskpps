import { memo, type CSSProperties } from 'react';
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
 * Pipeline 根容器端口组
 *
 * v5 (2026-07): Handle 是 React Flow 边的锚点，只读时不能移除，
 * 否则 Start→Pipeline→End 的连线全部消失；只读时透明且不可连接。
 * v6 (2026-07): 端口方位改为 上 in / 下 out，与 TB 布局一致。
 */
function PipelineHandles({ readOnly }: { readOnly: boolean }) {
  const base: CSSProperties = {
    width: 8,
    height: 8,
    background: 'transparent',
    borderRadius: '50%',
    ...(readOnly ? { opacity: 0, pointerEvents: 'none' } : null),
  };
  return (
    <>
      {/* In 端口（入口）— 顶部 */}
      <Handle
        id="in"
        type="target"
        position={Position.Top}
        isConnectable={!readOnly}
        style={{ ...base, border: '2px solid #64748b' }}
      />

      {/* Out 端口 — 底部 */}
      <Handle
        id="out"
        type="source"
        position={Position.Bottom}
        isConnectable={!readOnly}
        style={{ ...base, border: '2px solid #64748b' }}
      />

      {/* Post 端口 — 底部偏右（与 out 错开） */}
      <Handle
        id="post"
        type="source"
        position={Position.Bottom}
        isConnectable={!readOnly}
        style={{ ...base, border: '2px solid #ef4444', left: '75%', transform: 'translateX(-50%)' }}
      />
    </>
  );
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
      <PipelineHandles readOnly={readOnly} />

      {/* 标题 */}
      {/* v2 (2026-07): 超长流水线名溢出容器（截图验证），加 ellipsis 截断 */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          left: 12,
          right: 12,
          fontFamily: FONT_MONO,
          fontSize: 12,
          fontWeight: 600,
          color: '#64748b',
          letterSpacing: 0.5,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </div>
    </div>
  );
}

export default memo(EditorPipelineNode);
