import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';
import { useReadOnly } from './ReadOnlyContext';

interface EditorStartEndNodeData {
  variant: 'start' | 'end';
  [key: string]: unknown;
}

/**
 * Start / End 哨兵节点 — 胶囊形
 */
function EditorStartEndNode({ data, selected }: { data: EditorStartEndNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const isStart = data.variant === 'start';
  const dotColor = isStart ? '#10B981' : '#94A3B8';
  const borderColor = selected ? '#1677ff' : '#94a3b8';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 12px',
        border: `1.5px solid ${borderColor}`,
        borderRadius: 24,
        background: '#ffffff',
        fontFamily: FONT_MONO,
        fontSize: 11,
        fontWeight: 600,
        color: '#475569',
        letterSpacing: 0.8,
        boxShadow: selected && !readOnly ? '0 0 0 4px rgba(22,119,255,0.12)' : undefined,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          backgroundColor: dotColor,
          flexShrink: 0,
        }}
      />
      <span>{isStart ? 'START' : 'END'}</span>

      {/* v2 (2026-07): Handle 是 React Flow 边锚点，只读时不能移除，
          否则 START→Pipeline / Pipeline→END 的连线消失；透明且不可连接。
          v3 (2026-07): start 的 out 改到底部、end 的 in 改到顶部，与 TB 布局一致 */}
      {isStart ? (
        <Handle
          id="out"
          type="source"
          position={Position.Bottom}
          isConnectable={!readOnly}
          style={{
            width: 8,
            height: 8,
            background: 'transparent',
            border: '2px solid #64748b',
            borderRadius: '50%',
            ...(readOnly ? { opacity: 0, pointerEvents: 'none' } : null),
          }}
        />
      ) : (
        <Handle
          id="in"
          type="target"
          position={Position.Top}
          isConnectable={!readOnly}
          style={{
            width: 8,
            height: 8,
            background: 'transparent',
            border: '2px solid #64748b',
            borderRadius: '50%',
            ...(readOnly ? { opacity: 0, pointerEvents: 'none' } : null),
          }}
        />
      )}
    </div>
  );
}

export default memo(EditorStartEndNode);
