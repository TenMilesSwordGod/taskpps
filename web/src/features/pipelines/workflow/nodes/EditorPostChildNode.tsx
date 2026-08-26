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
  on_fail: { accent: '#ef4444', soft: '#FEE2E2', label: '失败时' },
  on_success: { accent: '#22c55e', soft: '#DCFCE7', label: '成功时' },
  always: { accent: '#6b7280', soft: '#F1F5F9', label: '始终' },
};

/**
 * Post 子容器节点
 *
 * v2 (2026-07): 移除 emoji，使用纯文字标签（无 emoji 图标）
 * v9 (2026-08): n8n 化 —— 彩底彩框卡退役，统一白卡 + 发丝边框语言
 * （与 Task 卡一致）；变体语义由徽章 chip + 变体色圆点承载，
 * 视觉噪音更低且与主画布卡片浑然一体
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
        // v9: 发丝边框白卡（变体色只出现在 chip 与圆点小面积上）
        border: '1px solid #E2E8F0',
        borderRadius: 8,
        background: '#FFFFFF',
        padding: '8px 10px',
        position: 'relative',
        boxShadow: selected && !readOnly ? `0 0 0 2px ${style.accent}30` : undefined,
      }}
    >
      {/* 变体色圆点 —— 右上角小面积变体标识 */}
      <span
        aria-hidden
        style={{
          position: 'absolute',
          top: 8,
          right: 8,
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: style.accent,
        }}
      />
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
            border: `2px solid ${style.accent}`,
            borderRadius: '50%',
            left: -6,
            top: '50%',
          }}
        />
      )}

      {/* 标题 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span
          style={{
            padding: '1px 6px',
            borderRadius: 4,
            background: style.soft,
            color: style.accent,
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
            color: '#262626',
          }}
        >
          {taskName}
        </span>
      </div>
    </div>
  );
}

export default memo(EditorPostChildNode);
