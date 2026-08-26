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
 * Post 父容器节点 — 软红实线边框
 * 仅左侧 in 端口（接收 Post 连线），无 out / post 端口
 *
 * v2 (2026-07): SVG 图标替换 emoji + 折叠/展开支持
 * v9 (2026-08): n8n 化 —— 虚线/刺眼纯红退役，改软红实线（red-300）+ 浅红底；
 * 缩放手柄仅选中可见（isVisible 默认 true 导致的常驻蓝方块问题）
 */
function EditorPostParentNode({ data, selected }: { data: EditorPostParentNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const label = data.label || 'Post';
  const borderColor = selected ? '#DC2626' : '#FCA5A5';
  const collapsed = data.collapsed === true;

  if (collapsed) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          border: `2px solid ${borderColor}`,
          borderRadius: 8,
          background: '#FFF5F5',
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          minWidth: 100,
          minHeight: 40,
        }}
      >
        {!readOnly && <NodeResizer isVisible={!!selected} minWidth={100} minHeight={40} />}
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
        border: `1.5px solid ${borderColor}`,
        borderRadius: 12,
        background: '#FFF5F5',
        position: 'relative',
        boxShadow: selected && !readOnly ? '0 0 0 2px rgba(239,68,68,0.15)' : undefined,
        minWidth: 200,
        minHeight: 150,
      }}
    >
      {!readOnly && <NodeResizer isVisible={!!selected} minWidth={200} minHeight={150} />}
      {/* 注意(2026-07): 只读模式下隐藏 Handle */}
      {!readOnly && (
        <Handle
          id="in"
          type="target"
          position={Position.Left}
          style={{
            width: 10,
            height: 10,
            background: '#FFFFFF',
            border: '2px solid #ef4444',
            borderRadius: '50%',
            left: -6,
            top: '50%',
          }}
        />
      )}

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
