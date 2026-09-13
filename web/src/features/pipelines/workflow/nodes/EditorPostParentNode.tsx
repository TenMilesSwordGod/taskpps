import { memo } from 'react';
import { Handle, Position, NodeResizer } from '@xyflow/react';
import { FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';
import { PostParentIcon } from '../icons';
import { useReadOnly } from './ReadOnlyContext';

interface EditorPostParentNodeData {
  label?: string;
  parentTaskId?: string;
  collapsed?: boolean;
  [key: string]: unknown;
}

/**
 * Post 父容器端口（仅 in）
 *
 * v3 (2026-07): Handle 是 React Flow 边锚点，只读/折叠时移除会导致
 * SubPipeline→Post 的路由连线消失；只读时透明且不可连接。
 * v4 (2026-07): in 端口改到顶部，与 TB 布局一致。
 */
function PostParentHandles({ readOnly }: { readOnly: boolean }) {
  return (
    <Handle
      id="in"
      type="target"
      position={Position.Top}
      isConnectable={!readOnly}
      style={{
        width: 8,
        height: 8,
        background: 'transparent',
        border: '2px solid #ef4444',
        borderRadius: '50%',
        ...(readOnly ? { opacity: 0, pointerEvents: 'none' } : null),
      }}
    />
  );
}

/**
 * Post 父容器节点 — 红色虚线边框
 * 仅左侧 in 端口（接收 Post 连线），无 out / post 端口
 *
 * v2 (2026-07): SVG 图标替换 emoji + 折叠/展开支持
 */
function EditorPostParentNode({ data, selected }: { data: EditorPostParentNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const label = data.label || 'Post';
  const borderStyle = readOnly ? 'solid' : 'dashed';
  const borderColor = selected ? '#b91c1c' : '#ef4444';
  const collapsed = data.collapsed === true;

  if (collapsed) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          border: `2px solid ${borderColor}`,
          borderRadius: 8,
          background: '#fef2f2',
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          minWidth: 100,
          minHeight: 40,
        }}
      >
        {!readOnly && <NodeResizer minWidth={100} minHeight={40} />}
        <PostParentHandles readOnly={readOnly} />
        <PostParentIcon style={{ width: 16, height: 16, color: '#ef4444' }} />
        <span style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: 600, color: '#991b1b' }}>
          {label}
        </span>
      </div>
    );
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        border: `2px ${borderStyle} ${borderColor}`,
        borderRadius: 12,
        background: '#fef2f2',
        position: 'relative',
        boxShadow: selected && !readOnly ? '0 0 0 4px rgba(239,68,68,0.12)' : undefined,
        minWidth: 200,
        minHeight: 150,
      }}
    >
      {!readOnly && <NodeResizer minWidth={200} minHeight={150} />}
      <PostParentHandles readOnly={readOnly} />

      {/* 标题 */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          left: 12,
          right: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {/* v2 (2026-07): SVG 图标替换 emoji */}
          <PostParentIcon style={{ width: 18, height: 18, color: '#ef4444' }} />
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 13,
              fontWeight: 700,
              color: '#991b1b',
            }}
          >
            {label}
          </span>
        </div>
      </div>
    </div>
  );
}

export default memo(EditorPostParentNode);
