import { memo, type CSSProperties } from 'react';
import { Handle, Position, NodeResizer } from '@xyflow/react';
import type { TaskYAML, TaskType } from '@/types';
import { TYPE_COLOR, FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';
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
/**
 * Task 节点端口组
 *
 * v3 (2026-07): Handle 必须始终渲染 —— React Flow 的边依赖 Handle 作为锚点，
 * 原实现只读模式移除 Handle，导致查看模式所有连线消失（压测截图暴露）。
 * 只读时改为透明且不可连接（边仍可正确锚定），折叠态同样需要端口，
 * 否则折叠节点的入/出边也会消失。
 * v4 (2026-07): 端口方位改为 上 in / 下 out，与 TB（从上到下）布局一致。
 * 原左右端口使所有边在节点两侧绕行（截图暴露的交叉/绕线问题）。
 */
function TaskHandles({ readOnly }: { readOnly: boolean }) {
  const base: CSSProperties = {
    width: 8,
    height: 8,
    background: 'transparent',
    borderRadius: '50%',
    ...(readOnly ? { opacity: 0, pointerEvents: 'none' } : null),
  };
  return (
    <>
      {/* In 端口 — 顶部（接收上游） */}
      <Handle
        id="in"
        type="target"
        position={Position.Top}
        isConnectable={!readOnly}
        style={{ ...base, border: '2px solid #64748b' }}
      />

      {/* Out 端口 — 底部（连向下游） */}
      <Handle
        id="out"
        type="source"
        position={Position.Bottom}
        isConnectable={!readOnly}
        style={{ ...base, border: '2px solid #64748b' }}
      />

      {/* Post 端口 — 底部偏右（与 out 错开，用于挂接 Post） */}
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
        <TaskHandles readOnly={readOnly} />
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
      <TaskHandles readOnly={readOnly} />

      {/* 标题行 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, minWidth: 0 }}>
        {/* v2 (2026-07): SVG 图标替换 emoji */}
        {IconComponent && <IconComponent style={{ width: 16, height: 16, color: iconColor, flexShrink: 0 }} />}
        {/* v3 (2026-07): 超长任务名会把节点宽度撑爆并溢出父容器（截图验证），
            限制标题最大宽度，超出部分 ellipsis */}
        <span
          style={{
            fontFamily: FONT_MONO,
            fontSize: 13,
            fontWeight: 600,
            color: '#0f172a',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: 150,
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
      {/* v2 (2026-07): 原 slice(0,25) 截断无省略号，长条件看起来像语法错误；
          改为 CSS ellipsis 完整内容 + 视觉省略号 */}
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
            maxWidth: '100%',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            boxSizing: 'border-box',
            verticalAlign: 'bottom',
          }}
        >
          {task.when}
        </div>
      )}
    </div>
  );
}

export default memo(EditorTaskNode);
