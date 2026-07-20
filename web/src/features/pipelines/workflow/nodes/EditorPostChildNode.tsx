import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { TaskYAML, TaskType } from '@/types';
import { FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';

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
        boxShadow: selected ? `0 0 0 4px ${style.accent}20` : undefined,
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
          border: `2px solid ${style.accent}`,
          borderRadius: '50%',
          left: -5,
          top: '50%',
        }}
      />

      {/* 标题 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span
          style={{
            padding: '1px 6px',
            borderRadius: 4,
            background: style.accent,
            color: '#fff',
            fontSize: 10,
            fontFamily: FONT_MONO,
            fontWeight: 600,
          }}
        >
          {style.label}
        </span>
        <span
          style={{
            fontFamily: FONT_MONO,
            fontSize: 12,
            fontWeight: 600,
            color: '#0f172a',
          }}
        >
          {taskName}
        </span>
      </div>
    </div>
  );
}

export default memo(EditorPostChildNode);
