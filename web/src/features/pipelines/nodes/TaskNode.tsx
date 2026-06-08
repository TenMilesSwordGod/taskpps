import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Tag, Tooltip } from 'antd';
import {
  Terminal,
  Code2,
  ListOrdered,
  GitBranch,
  Upload,
} from 'lucide-react';
import type { TaskYAML, TaskType, TaskStatus } from '@/types';
import { useAppStore } from '@/stores/appStore';

/** 任务类型图标映射 */
const TASK_TYPE_ICON: Record<TaskType, React.ReactNode> = {
  command: <Terminal size={16} />,
  invoke: <Code2 size={16} />,
  steps: <ListOrdered size={16} />,
  git: <GitBranch size={16} />,
  nexus: <Upload size={16} />,
  ssh: <Terminal size={16} />,
};

/** 任务类型颜色映射 */
const TASK_TYPE_COLOR: Record<TaskType, string> = {
  command: '#8c8c8c',
  invoke: '#1677ff',
  steps: '#722ed1',
  git: '#fa8c16',
  nexus: '#13c2c2',
  ssh: '#8c8c8c',
};

/** 任务类型标签 */
const TASK_TYPE_LABEL: Record<TaskType, string> = {
  command: '命令',
  invoke: '调用',
  steps: '步骤',
  git: 'Git',
  nexus: 'Nexus',
  ssh: 'SSH',
};

/** 任务状态边框颜色 */
const STATUS_BORDER_COLOR: Record<TaskStatus, string> = {
  pending: '#d9d9d9',
  running: '#1677ff',
  success: '#52c41a',
  failed: '#ff4d4f',
  skipped: '#faad14',
  cancelled: '#ff4d4f',
};

/** 推断任务类型 */
function inferTaskType(task: TaskYAML): TaskType {
  if (task.invoke) return 'invoke';
  if (task.steps) return 'steps';
  if (task.git) return 'git';
  if (task.nexus) return 'nexus';
  return 'command';
}

/** 脉冲动画样式 */
const pulseStyle = `
@keyframes task-pulse {
  0% { box-shadow: 0 0 0 0 rgba(22, 119, 255, 0.4); }
  70% { box-shadow: 0 0 0 8px rgba(22, 119, 255, 0); }
  100% { box-shadow: 0 0 0 0 rgba(22, 119, 255, 0); }
}
`;

interface TaskNodeData {
  task: TaskYAML;
  subpipelineName: string;
  status?: TaskStatus;
  order?: number;
  [key: string]: unknown;
}

function TaskNodeComponent({ data, id }: { data: TaskNodeData; id: string }) {
  const { task, status, order } = data;
  const taskType = inferTaskType(task);
  const typeColor = TASK_TYPE_COLOR[taskType];
  const borderColor = status ? STATUS_BORDER_COLOR[status] : typeColor;
  const selectedNodeId = useAppStore((s) => s.selectedNodeId);
  const setSelectedNodeId = useAppStore((s) => s.setSelectedNodeId);
  const isSelected = selectedNodeId === id;

  const isRunning = status === 'running';

  return (
    <>
      {/* 注入脉冲动画 */}
      {isRunning && <style>{pulseStyle}</style>}

      <Handle type="target" position={Position.Top} className="!w-2 !h-2 !bg-gray-400" />

      <Tooltip title={`${task.name} (${TASK_TYPE_LABEL[taskType]})`}>
        <div
          onClick={(e) => {
            e.stopPropagation();
            setSelectedNodeId(id);
          }}
          className="flex items-center gap-2 px-3 py-2 bg-white rounded-lg shadow-sm cursor-pointer transition-all duration-200 hover:shadow-md select-none"
          style={{
            width: 200,
            border: `2px solid ${borderColor}`,
            animation: isRunning ? 'task-pulse 2s infinite' : undefined,
            outline: isSelected ? `2px solid ${typeColor}` : undefined,
            outlineOffset: '2px',
          }}
        >
          {/* 顺序编号 */}
          {order != null && (
            <div
              className="flex items-center justify-center w-6 h-6 rounded-full text-white text-xs font-bold shrink-0"
              style={{ backgroundColor: typeColor }}
            >
              {order}
            </div>
          )}

          {/* 类型图标 */}
          <div
            className="flex items-center justify-center w-7 h-7 rounded"
            style={{ color: typeColor }}
          >
            {TASK_TYPE_ICON[taskType]}
          </div>

          {/* 任务名 + 类型标签 */}
          <div className="flex flex-col min-w-0 flex-1">
            <span className="text-sm font-medium truncate text-gray-800">
              {task.name}
            </span>
            <Tag
              color={typeColor}
              className="text-xs leading-none mt-0.5"
              style={{ fontSize: 10, padding: '0 4px', lineHeight: '16px', border: 'none' }}
            >
              {TASK_TYPE_LABEL[taskType]}
            </Tag>
          </div>
        </div>
      </Tooltip>

      <Handle type="source" position={Position.Bottom} className="!w-2 !h-2 !bg-gray-400" />
    </>
  );
}

export default memo(TaskNodeComponent);
