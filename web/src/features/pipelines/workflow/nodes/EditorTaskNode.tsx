import { memo } from 'react';
import { Handle, Position, NodeResizer } from '@xyflow/react';
import type { TaskYAML, TaskType } from '@/types';
import { TYPE_COLOR, FONT_MONO, INK } from '@/features/pipelines/nodes/nodeTokens';
import { CmdIcon, StepIcon, PluginIcon, InvokeIcon } from '../icons';
import { useReadOnly } from './ReadOnlyContext';

/** 推断任务类型 */
function inferType(task: TaskYAML): TaskType {
  if (task.invoke) return 'invoke';
  if (task.steps) return 'steps';
  if (task.plugin) return 'plugin';
  if (task.git) return 'git';
  if (task.nexus) return 'nexus';
  return 'command';
}

/** v2 (2026-07): 类型 → SVG 图标组件映射（替换 emoji） */
const TYPE_ICON_SVG: Record<string, React.ComponentType<{ style?: React.CSSProperties }>> = {
  command: CmdIcon,
  invoke: InvokeIcon,
  steps: StepIcon,
  plugin: PluginIcon,
};

interface EditorTaskNodeData {
  task?: TaskYAML;
  taskType?: TaskType;
  subpipelineName?: string;
  collapsed?: boolean;
  [key: string]: unknown;
}

/**
 * 可编辑 Task 节点 — n8n 风格紧凑圆角方形
 * 左入右出端口，底部 Post 端口
 *
 * v2 (2026-07): SVG 图标替换 emoji + 折叠支持
 */
function EditorTaskNode({ data, selected }: { data: EditorTaskNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const task = data.task;
  const taskName = task?.name || 'Task';
  const taskType = data.taskType || (task ? inferType(task) : 'command');
  const iconColor = TYPE_COLOR[taskType] || '#94a3b8';
  // 注意(2026-07): 只读模式下使用实线边框（与 PipelineGraph 查看模式一致），
  // 编辑模式使用虚线边框以暗示可拖拽/可连接
  const borderStyle = readOnly ? 'solid' : 'dashed';
  const borderColor = selected ? (readOnly ? '#64748b' : '#1677ff') : '#22c55e';
  const collapsed = data.collapsed === true;
  // v2 (2026-07): 使用 SVG 图标组件
  const IconComponent = TYPE_ICON_SVG[taskType];

  if (collapsed) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          border: `2px ${borderStyle} ${borderColor}`,
          borderRadius: 8,
          background: '#f0fdf4',
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
        {IconComponent && <IconComponent style={{ width: 14, height: 14, color: iconColor }} />}
        <span style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: 600, color: '#0f172a' }}>
          {taskName}
        </span>
      </div>
    );
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        minWidth: 100,
        minHeight: 56,
        border: `2px ${borderStyle} ${borderColor}`,
        borderRadius: 8,
        background: '#f0fdf4',
        padding: '10px 12px',
        position: 'relative',
        boxShadow: selected && !readOnly ? '0 0 0 4px rgba(22,119,255,0.12)' : undefined,
        boxSizing: 'border-box',
      }}
    >
      {!readOnly && <NodeResizer minWidth={100} minHeight={56} />}
      {/* 注意(2026-07): 只读模式下隐藏所有 Handle，与 PipelineGraph 查看模式一致 */}
      {!readOnly && (
        <>
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
        </>
      )}

      {/* 标题行 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        {/* v2 (2026-07): SVG 图标替换 emoji */}
        {IconComponent && <IconComponent style={{ width: 16, height: 16, color: iconColor }} />}
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
