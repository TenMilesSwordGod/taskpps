import { useMemo } from 'react';
import { Popover, Progress, Tag, Space } from 'antd';
import { CheckCircle2, AlertCircle, Loader2, CircleDot, MinusCircle } from 'lucide-react';
import type { TaskRunResponse, TaskStatus } from '@/types';

/** 状态中文标签 */
const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: '等待中',
  running: '运行中',
  success: '成功',
  failed: '失败',
  skipped: '已跳过',
  cancelled: '已取消',
};

/** 状态颜色 */
const STATUS_COLOR: Record<TaskStatus, string> = {
  pending: '#9ca3af',
  running: '#3b82f6',
  success: '#10b981',
  failed: '#ef4444',
  skipped: '#f59e0b',
  cancelled: '#f97316',
};

const ALL_STATUSES: TaskStatus[] = ['running', 'success', 'failed', 'skipped', 'cancelled', 'pending'];

interface Props {
  /** 完整任务列表（详情页可用） */
  tasks?: TaskRunResponse[];
  /** 任务状态计数摘要（列表页可用，优先级低于 tasks） */
  taskSummary?: Record<string, number>;
  children: React.ReactNode;
}

export default function PipelineProgressPopover({ tasks, taskSummary, children }: Props) {
  const stats = useMemo(() => {
    const counts: Record<TaskStatus, number> = {
      pending: 0, running: 0, success: 0, failed: 0, skipped: 0, cancelled: 0,
    };

    // 优先使用完整 tasks 数据
    if (tasks && tasks.length > 0) {
      for (const t of tasks) {
        counts[t.status]++;
      }
      return counts;
    }

    // 回退到 task_summary
    if (taskSummary && Object.keys(taskSummary).length > 0) {
      for (const [status, count] of Object.entries(taskSummary)) {
        if (status in counts) {
          counts[status as TaskStatus] = count;
        }
      }
      return counts;
    }

    return null;
  }, [tasks, taskSummary]);

  // 无数据时不显示悬浮窗
  if (!stats) return <>{children}</>;

  const total = Object.values(stats).reduce((a, b) => a + b, 0);
  if (total === 0) return <>{children}</>;

  const done = stats.success + stats.skipped + stats.failed + stats.cancelled;
  const percent = Math.round((done / total) * 100);
  const isFailed = stats.failed > 0;
  const isDone = done === total;

  const strokeColor = isFailed ? '#ef4444' : isDone ? '#10b981' : '#3b82f6';

  const content = (
    <div style={{ minWidth: 200 }}>
      {/* 进度条 */}
      <div style={{ marginBottom: 8 }}>
        <Progress
          percent={percent}
          strokeColor={strokeColor}
          size="small"
          status={isFailed ? 'exception' : isDone ? 'success' : 'active'}
        />
      </div>

      {/* 状态统计 */}
      <Space size={4} wrap>
        {stats.running > 0 && (
          <Tag icon={<Loader2 size={10} className="animate-spin" />} color="processing" style={{ margin: 0, fontSize: 11 }}>
            运行中 {stats.running}
          </Tag>
        )}
        {stats.success > 0 && (
          <Tag icon={<CheckCircle2 size={10} />} color="success" style={{ margin: 0, fontSize: 11 }}>
            成功 {stats.success}
          </Tag>
        )}
        {stats.failed > 0 && (
          <Tag icon={<AlertCircle size={10} />} color="error" style={{ margin: 0, fontSize: 11 }}>
            失败 {stats.failed}
          </Tag>
        )}
        {stats.skipped > 0 && (
          <Tag icon={<MinusCircle size={10} />} color="warning" style={{ margin: 0, fontSize: 11 }}>
            跳过 {stats.skipped}
          </Tag>
        )}
        {stats.cancelled > 0 && (
          <Tag color="default" style={{ margin: 0, fontSize: 11 }}>
            取消 {stats.cancelled}
          </Tag>
        )}
        {stats.pending > 0 && (
          <Tag icon={<CircleDot size={10} />} color="default" style={{ margin: 0, fontSize: 11 }}>
            等待 {stats.pending}
          </Tag>
        )}
      </Space>

      {/* 任务列表（仅 tasks 模式可用） */}
      {tasks && tasks.length > 0 && (
        <div style={{ marginTop: 8, maxHeight: 160, overflowY: 'auto' }}>
          {tasks.map((t) => (
            <div
              key={t.task_name}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '2px 0',
                fontSize: 12,
                color: STATUS_COLOR[t.status],
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: STATUS_COLOR[t.status],
                  flexShrink: 0,
                }}
              />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {t.task_name}
              </span>
              <span style={{ marginLeft: 'auto', flexShrink: 0, fontSize: 11, color: '#9ca3af' }}>
                {STATUS_LABEL[t.status]}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <Popover
      content={content}
      title="任务进度"
      mouseEnterDelay={2}
      mouseLeaveDelay={0.3}
      placement="right"
    >
      {children}
    </Popover>
  );
}
