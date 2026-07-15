import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Tooltip } from 'antd';
import type { TaskYAML, TaskType, TaskStatus } from '@/types';
import { useAppStore } from '@/stores/appStore';
import {
  NODE_SIZE,
  INK,
  STATUS_COLOR,
  STATUS_SOFT_BG,
  STATUS_LABEL,
  TYPE_LABEL,
  FONT_MONO,
} from './nodeTokens';

/** 推断任务类型（仅用于 Tooltip） */
function inferTaskType(task: TaskYAML): TaskType {
  if (task.invoke) return 'invoke';
  if (task.steps) return 'steps';
  if (task.plugin) return 'plugin';
  if (task.git) return 'git';
  if (task.nexus) return 'nexus';
  return 'command';
}

/** 运行中脉冲动画 — v2 (2026-07) 对齐 design-tokens: animation.node_pulse */
const pulseStyle = `
@keyframes task-border-pulse {
  0%, 100% { border-color: #0EA5E9; box-shadow: 0 0 0 0 rgba(14,165,233,0.4); }
  50% { border-color: #7DD3FC; box-shadow: 0 0 0 6px rgba(14,165,233,0); }
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
  const { task, status } = data;
  const taskType = inferTaskType(task);
  const selectedNodeId = useAppStore((s) => s.selectedNodeId);
  const setSelectedNodeId = useAppStore((s) => s.setSelectedNodeId);
  const isSelected = selectedNodeId === id;
  const isRunning = status === 'running';

  // 状态驱动整卡：边框色 + 极淡背景晕染（参考 Argo CD / GitHub Actions）
  const borderColor = isSelected
    ? INK.accent
    : status
      ? STATUS_COLOR[status]
      : INK.border;
  const cardBg = status ? STATUS_SOFT_BG[status] : '#FFFFFF';

  return (
    <>
      {isRunning && <style>{pulseStyle}</style>}

      <Handle
        type="target"
        position={Position.Top}
        className="!w-1.5 !h-1.5 !bg-slate-300 !border-0 !-top-[3px]"
      />
      {/* 左侧 target handle —— no 边专用，让跳过路径从左侧进入而非顶部 */}
      <Handle
        id="left"
        type="target"
        position={Position.Left}
        className="!w-1.5 !h-1.5 !bg-slate-300 !border-0 !-left-[3px]"
      />

      <Tooltip
        title={
          <span style={{ fontFamily: FONT_MONO, fontSize: 11 }}>
            {task.name} · {TYPE_LABEL[taskType]}
            {status ? ` · ${STATUS_LABEL[status]}` : ''}
          </span>
        }
      >
        <div
          onClick={(e) => {
            e.stopPropagation();
            setSelectedNodeId(id);
          }}
          className="relative flex items-center justify-center bg-white cursor-pointer select-none transition-colors duration-150"
          style={{
            width: NODE_SIZE.TASK_W,
            height: NODE_SIZE.TASK_H,
            border: `1.5px solid ${borderColor}`,
            borderRadius: 6,
            backgroundColor: cardBg,
            boxShadow: isSelected && !isRunning ? `inset 0 0 0 1px ${INK.accent}55` : undefined,
            animation: isRunning ? 'task-border-pulse 1.6s ease-in-out infinite' : undefined,
          }}
        >
          {/* 任务名（居中，等宽 —— CI/CD job 名本身即代码） */}
          <span
            className="px-3 max-w-full truncate text-center"
            style={{
              fontFamily: FONT_MONO,
              fontSize: 12,
              fontWeight: 600,
              color: INK.textPrimary,
              letterSpacing: -0.1,
            }}
          >
            {task.name}
          </span>
        </div>
      </Tooltip>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-1.5 !h-1.5 !bg-slate-300 !border-0 !-bottom-[3px]"
      />
    </>
  );
}

export default memo(TaskNodeComponent);
