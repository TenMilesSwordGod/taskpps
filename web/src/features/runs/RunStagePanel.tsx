import { useMemo } from 'react';
import { Tooltip } from 'antd';
import { ChevronRight } from 'lucide-react';
import type { PipelineDetail, TaskRunResponse, TaskStatus } from '@/types';

const STATUS_META: Record<TaskStatus, { color: string; label: string }> = {
  pending: { color: '#9ca3af', label: '等待中' },
  running: { color: '#3b82f6', label: '运行中' },
  success: { color: '#10b981', label: '成功' },
  failed: { color: '#ef4444', label: '失败' },
  skipped: { color: '#f59e0b', label: '已跳过' },
  cancelled: { color: '#f97316', label: '已取消' },
};

interface StageNode {
  taskId: string;
  name: string;
  subpipeline: string;
  status: TaskStatus;
}

interface RunStagePanelProps {
  pipeline?: PipelineDetail;
  taskRuns?: TaskRunResponse[];
}

const BREATHING_STYLE = `
@keyframes stage-breathing {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(59,130,246,0.4); }
  50% { opacity: 0.85; box-shadow: 0 0 0 3px rgba(59,130,246,0); }
}
@media (prefers-reduced-motion: reduce) {
  .stage-breathing { animation: none !important; }
}
`;

/** 运行历史详情页顶部的小面板：按流水线定义顺序展示任务节点状态 */
export default function RunStagePanel({ pipeline, taskRuns }: RunStagePanelProps) {
  const stages = useMemo<StageNode[]>(() => {
    const runMap = new Map<string, TaskRunResponse>();
    for (const t of taskRuns ?? []) {
      runMap.set(t.task_name, t);
    }

    const list: StageNode[] = [];
    const seen = new Set<string>();

    const pushTask = (subpipeline: string, name: string) => {
      const taskId = subpipeline ? `${subpipeline}.${name}` : name;
      seen.add(taskId);
      list.push({
        taskId,
        name,
        subpipeline,
        status: runMap.get(taskId)?.status ?? 'pending',
      });
    };

    if (pipeline?.pipelines) {
      for (const sub of pipeline.pipelines) {
        for (const task of sub.tasks) {
          pushTask(sub.name, task.name);
        }
      }
    }

    if (pipeline?.tasks) {
      for (const task of pipeline.tasks) {
        pushTask('', task.name);
      }
    }

    // 兜底：运行记录里有但快照定义里没有的任务，按原顺序追加到末尾
    for (const t of taskRuns ?? []) {
      if (!seen.has(t.task_name)) {
        list.push({
          taskId: t.task_name,
          name: t.task_name.includes('.') ? t.task_name.split('.').pop()! : t.task_name,
          subpipeline: t.subpipeline_name,
          status: t.status,
        });
      }
    }

    return list;
  }, [pipeline, taskRuns]);

  if (stages.length === 0) return null;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        minWidth: 0,
        maxWidth: 480,
        padding: '4px 8px',
        background: '#f9fafb',
        border: '1px solid #e5e7eb',
        borderRadius: 16,
        overflowX: 'auto',
        scrollbarWidth: 'none',
        msOverflowStyle: 'none',
      }}
    >
      <style>{BREATHING_STYLE}</style>
      {stages.map((stage, index) => {
        const meta = STATUS_META[stage.status];
        const isLast = index === stages.length - 1;
        const tooltip = `${stage.subpipeline ? `${stage.subpipeline} / ` : ''}${stage.name} · ${meta.label}`;

        return (
          <div key={stage.taskId} style={{ display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0 }}>
            <Tooltip title={tooltip}>
              <span
                data-testid="stage-node"
                data-task-name={stage.taskId}
                data-status={stage.status}
                className={stage.status === 'running' ? 'stage-breathing' : undefined}
                style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: meta.color,
                  cursor: 'default',
                  ...(stage.status === 'running'
                    ? { animation: 'stage-breathing 2s ease-in-out infinite' }
                    : {}),
                }}
              />
            </Tooltip>
            {!isLast && <ChevronRight size={12} color="#d1d5db" />}
          </div>
        );
      })}
    </div>
  );
}
