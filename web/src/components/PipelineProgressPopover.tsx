import { useState, useMemo, useCallback, useRef } from 'react';
import { Popover, Spin } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import type { TaskRunResponse, TaskStatus } from '@/types';

/** 状态颜色 — 绿=通过，灰=未执行，红=失败，蓝=运行中，黄=跳过，橙=取消 */
const STATUS_COLOR: Record<TaskStatus, string> = {
  success: '#10b981',
  failed: '#ef4444',
  running: '#3b82f6',
  pending: '#9ca3af',
  skipped: '#9ca3af',
  cancelled: '#f97316',
};

/** 子流水线状态汇总颜色（优先级：failed > running > 其他） */
function groupStatusColor(tasks: TaskRunResponse[]): string {
  if (tasks.some((t) => t.status === 'failed')) return '#ef4444';
  if (tasks.some((t) => t.status === 'running')) return '#3b82f6';
  return '#10b981';
}

/** 按 subpipeline_name 分组，保持顺序 */
function groupBySubpipeline(tasks: TaskRunResponse[]): Map<string, TaskRunResponse[]> {
  const map = new Map<string, TaskRunResponse[]>();
  for (const t of tasks) {
    const key = t.subpipeline_name || '';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(t);
  }
  return map;
}

interface Props {
  /** 运行 ID（列表页传入，用于懒加载任务详情） */
  runId?: string;
  /** 完整任务列表（详情页可用，跳过懒加载） */
  tasks?: TaskRunResponse[];
  /** 任务状态计数摘要（列表页可用，无 runId 时作为 fallback） */
  taskSummary?: Record<string, number>;
  children: React.ReactNode;
}

export default function PipelineProgressPopover({ runId, tasks, taskSummary, children }: Props) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  // 每次 hover 时从 API 获取最新任务详情
  const [loadedTasks, setLoadedTasks] = useState<TaskRunResponse[] | null>(null);
  const [loading, setLoading] = useState(false);
  const fetchingRef = useRef(false);

  const handleOpenChange = useCallback(async (visible: boolean) => {
    setOpen(visible);
    if (!visible || !runId) return;

    // 防止重复请求（上一次请求尚未完成）
    if (fetchingRef.current) return;

    setLoading(true);
    fetchingRef.current = true;
    try {
      const res = await fetch(`/api/runs/${runId}`);
      if (res.ok) {
        const data = await res.json();
        setLoadedTasks(data.tasks ?? []);
        // 顺便写入缓存
        queryClient.setQueryData(['run', runId], data);
      }
    } catch {
      // 静默失败
    } finally {
      setLoading(false);
      fetchingRef.current = false;
    }
  }, [runId, queryClient]);

  // 实际使用的任务列表：优先使用最新获取的数据，其次使用 tasks prop
  const effectiveTasks = useMemo(() => {
    if (loadedTasks && loadedTasks.length > 0) return loadedTasks;
    if (tasks && tasks.length > 0) return tasks;
    return null;
  }, [loadedTasks, tasks]);

  // 按子流水线分组
  const groups = useMemo(() => {
    if (!effectiveTasks) return null;
    return groupBySubpipeline(effectiveTasks);
  }, [effectiveTasks]);

  // 无数据判断
  const hasData = useMemo(() => {
    if (effectiveTasks && effectiveTasks.length > 0) return true;
    if (taskSummary && Object.keys(taskSummary).length > 0) return true;
    return false;
  }, [effectiveTasks, taskSummary]);

  if (!hasData && !runId) return <>{children}</>;

  const content = (
    <div style={{ minWidth: 220, maxWidth: 340, padding: '4px 0' }}>
      {loading && (
        <div style={{ textAlign: 'center', padding: '16px 0' }}>
          <Spin size="small" />
        </div>
      )}

      {!loading && groups && groups.size > 0 && (
        <div style={{ maxHeight: 320, overflowY: 'auto' }}>
          {[...groups.entries()].map(([subpipeline, subTasks]) => (
            <div key={subpipeline} style={{ marginBottom: 8 }}>
              {/* 子流水线标题 */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                marginBottom: 4,
                paddingBottom: 3,
                borderBottom: '1px solid #f0f0f0',
              }}>
                <span style={{
                  width: 8,
                  height: 8,
                  borderRadius: 2,
                  background: groupStatusColor(subTasks),
                  flexShrink: 0,
                }} />
                <span style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: '#171717',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {subpipeline || '主流水线'}
                </span>
                <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 'auto', flexShrink: 0 }}>
                  {subTasks.filter((t) => t.status === 'success').length}/{subTasks.length}
                </span>
              </div>

              {/* 任务列表 */}
              {subTasks.map((t) => (
                <div
                  key={t.task_name}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '2px 0 2px 14px',
                    fontSize: 12,
                  }}
                >
                  <span style={{
                    width: 5,
                    height: 5,
                    borderRadius: '50%',
                    background: STATUS_COLOR[t.status],
                    flexShrink: 0,
                  }} />
                  <span style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    color: STATUS_COLOR[t.status],
                    flex: 1,
                  }}>
                    {t.task_name.includes('.') ? t.task_name.split('.').pop() : t.task_name}
                  </span>
                  {t.status === 'failed' && (
                    <span style={{ fontSize: 10, color: '#ef4444', flexShrink: 0 }}>FAIL</span>
                  )}
                  {t.status === 'running' && (
                    <span style={{ fontSize: 10, color: '#3b82f6', flexShrink: 0 }}>RUN</span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* fallback：无 tasks 数据时显示 taskSummary 计数 */}
      {!loading && !groups && taskSummary && Object.keys(taskSummary).length > 0 && (
        <div style={{ padding: '4px 0' }}>
          {Object.entries(taskSummary).map(([status, count]) => (
            <div key={status} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, padding: '2px 0' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: STATUS_COLOR[status as TaskStatus] || '#9ca3af', flexShrink: 0 }} />
              <span style={{ color: '#404040', flex: 1 }}>{status}</span>
              <span style={{ fontWeight: 600, color: STATUS_COLOR[status as TaskStatus] || '#9ca3af' }}>{count}</span>
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
      trigger="hover"
      open={open}
      onOpenChange={handleOpenChange}
      mouseEnterDelay={0.3}
      mouseLeaveDelay={0.3}
      placement="right"
      arrow
    >
      {children}
    </Popover>
  );
}
