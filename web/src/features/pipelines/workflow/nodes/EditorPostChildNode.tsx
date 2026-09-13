import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { TaskYAML, TaskType } from '@/types';
import { FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';
import { useReadOnly } from './ReadOnlyContext';

interface EditorPostChildNodeData {
  task?: TaskYAML;
  taskType?: TaskType;
  postVariant?: 'on_fail' | 'on_success' | 'always';
  parentTaskId?: string;
  [key: string]: unknown;
}

const VARIANT_STYLE = {
  on_fail: { accent: '#ef4444', background: '#fef2f2', label: '失败时' },
  on_success: { accent: '#22c55e', background: '#f0fdf4', label: '成功时' },
  always: { accent: '#6b7280', background: '#f9fafb', label: '始终' },
};

/**
 * Post 子容器节点
 *
 * v2 (2026-07): 移除 emoji，使用纯文字标签（无 emoji 图标）
 */
function EditorPostChildNode({ data, selected }: { data: EditorPostChildNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const task = data.task;
  const taskName = task?.name || 'Post Task';
  const variant = data.postVariant || 'on_fail';
  const style = VARIANT_STYLE[variant];

  return (
    <div
      style={{
        width: '100%',
        minWidth: 180,
        minHeight: 56,
        border: `1px solid ${style.accent}`,
        borderLeft: `3px solid ${style.accent}`,
        borderRadius: 6,
        background: style.background,
        padding: '8px 10px',
        position: 'relative',
        boxShadow: selected && !readOnly ? `0 0 0 4px ${style.accent}20` : undefined,
      }}
    >
      {/* v3 (2026-07): Handle 是 React Flow 边锚点，只读时不能移除；透明且不可连接 */}
      {/* v4 (2026-07): in 端口改到顶部，与 TB 布局一致 */}
      <Handle
        id="in"
        type="target"
        position={Position.Top}
        isConnectable={!readOnly}
        style={{
          width: 8,
          height: 8,
          background: 'transparent',
          border: `2px solid ${style.accent}`,
          borderRadius: '50%',
          ...(readOnly ? { opacity: 0, pointerEvents: 'none' } : null),
        }}
      />

      {/* 标题 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
        <span
          style={{
            padding: '1px 6px',
            borderRadius: 4,
            background: style.accent,
            color: '#fff',
            fontSize: 10,
            fontFamily: FONT_MONO,
            fontWeight: 600,
            flexShrink: 0,
          }}
        >
          {style.label}
        </span>
        {/* v2 (2026-07): 超长任务名撑爆节点宽度（与 EditorTaskNode 同类问题），加 ellipsis */}
        <span
          style={{
            fontFamily: FONT_MONO,
            fontSize: 12,
            fontWeight: 600,
            color: '#0f172a',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: 130,
          }}
        >
          {taskName}
        </span>
      </div>
    </div>
  );
}

export default memo(EditorPostChildNode);
