import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { TaskYAML, TaskType } from '@/types';
import { TYPE_COLOR, FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';

/** 推断任务类型 */
function inferType(task: TaskYAML): TaskType {
  if (task.invoke) return 'invoke';
  if (task.steps) return 'steps';
  if (task.plugin) return 'plugin';
  if (task.git) return 'git';
  if (task.nexus) return 'nexus';
  return 'command';
}

/** 类型标签 */
const TYPE_ICON: Record<TaskType, string> = {
  command: '⌨',
  invoke: '🔗',
  steps: '⚙',
  plugin: '🧩',
  git: '',
  nexus: '📦',
  ssh: '>_',
};

interface EditorTaskNodeData {
  task?: TaskYAML;
  taskType?: TaskType;
  subpipelineName?: string;
  [key: string]: unknown;
}

/**
 * 可编辑 Task 节点 — n8n 风格紧凑圆角方形
 * 左入右出端口，底部 Post 端口
 */
function EditorTaskNode({ data, selected }: { data: EditorTaskNodeData; selected?: boolean }) {
  const task = data.task;
  const taskName = task?.name || 'Task';
  const taskType = data.taskType || (task ? inferType(task) : 'command');
  const iconColor = TYPE_COLOR[taskType] || '#94a3b8';
  const borderColor = selected ? '#1677ff' : '#22c55e';

  return (
    <div
      style={{
        width: 180,
        minHeight: 56,
        border: `2px dashed ${borderColor}`,
        borderRadius: 8,
        background: '#f0fdf4',
        padding: '10px 12px',
        position: 'relative',
        boxShadow: selected ? '0 0 0 4px rgba(22,119,255,0.12)' : undefined,
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

      {/* 标题行 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{ fontSize: 13, color: iconColor, fontWeight: 600 }}>
          {TYPE_ICON[taskType]}
        </span>
        <span
          style={{
            fontFamily: FONT_MONO,
            fontSize: 13,
            fontWeight: 600,
            color: '#0f172a',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {taskName}
        </span>
      </div>

      {/* 副标题 */}
      <div
        style={{
          fontFamily: FONT_MONO,
          fontSize: 11,
          color: '#94a3b8',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          maxWidth: 150,
        }}
      >
        {task?.command
          ? task.command.slice(0, 20)
          : taskType === 'invoke'
            ? `invoke ${task?.invoke?.task || ''}`
            : taskType === 'steps'
              ? `${task?.steps?.length || 0} steps`
              : taskType === 'plugin'
                ? task?.plugin?.slice(0, 20)
                : taskType.toUpperCase()}
      </div>

      {/* when 标签 */}
      {task?.when && (
        <div
          style={{
            marginTop: 4,
            display: 'inline-block',
            padding: '1px 6px',
            borderRadius: 4,
            background: '#fef3c7',
            color: '#d97706',
            fontSize: 10,
            fontFamily: FONT_MONO,
          }}
        >
          {task.when.slice(0, 25)}
        </div>
      )}
    </div>
  );
}

export default memo(EditorTaskNode);
