import { useMemo, useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Breadcrumb, Button, Space, Spin, message, Popconfirm, Splitter, Tooltip, Tag } from 'antd';
import { XCircle, ListTree, RefreshCw, Copy, Clock } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useRun, useCancelRun, useRunLogs } from '@/api/runs';
import { usePipeline } from '@/api/pipelines';
import StatusTag from '@/components/StatusTag';
import LogViewer from './LogViewer';
import TaskTree from './TaskTree';
import { useSSELogs } from './hooks/useSSELogs';
import type { TaskStatus, RunResponse } from '@/types';
import type { LogEntry } from './hooks/useSSELogs';

/** 将 REST 日志响应转为 LogEntry[]（每条严格单行） */
function restLogsToEntries(logsMap: Record<string, string>): LogEntry[] {
  const entries: LogEntry[] = [];
  for (const [taskName, content] of Object.entries(logsMap)) {
    if (!content) continue;
    const lines = content.split(/\r\n|\r|\n/);
    for (const line of lines) {
      if (line.length === 0) continue;
      entries.push({ taskName, content: line, timestamp: 0 });
    }
  }
  return entries;
}

/** 计算任务进度 */
function calcProgress(run: RunResponse | undefined) {
  if (!run?.tasks?.length) return { done: 0, total: 0, failed: 0, running: 0 };
  let done = 0, failed = 0, running = 0;
  for (const t of run.tasks) {
    if (t.status === 'success' || t.status === 'skipped') done++;
    else if (t.status === 'failed' || t.status === 'cancelled') { done++; failed++; }
    else if (t.status === 'running') running++;
  }
  return { done, total: run.tasks.length, failed, running };
}

/** 把毫秒格式化为 mm:ss / hh:mm:ss */
function formatDuration(ms: number): string {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

/** 运行详情页面 */
export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: run, isLoading: runLoading } = useRun(id);
  const { data: pipeline } = usePipeline(run?.pipeline_file);
  const cancelRun = useCancelRun();
  const queryClient = useQueryClient();

  const [treeCollapsed, setTreeCollapsed] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const isLive = run?.status === 'running' || run?.status === 'pending';

  // SSE 实时日志（仅运行中/等待中）
  const sseResult = useSSELogs(isLive ? id : undefined);

  // REST 历史日志（仅非运行中）
  const { data: restLogs, refetch: refetchLogs, isFetching: logsFetching } = useRunLogs(!isLive ? id : undefined);

  // 合并日志：运行中用 SSE，否则用 REST
  const logs = useMemo(() => {
    if (isLive) return sseResult.logs;
    if (restLogs?.logs) return restLogsToEntries(restLogs.logs);
    return [];
  }, [isLive, sseResult.logs, restLogs?.logs]);

  const connected = isLive ? sseResult.connected : false;
  const autoScroll = isLive ? sseResult.autoScroll : true;
  const setAutoScroll = sseResult.setAutoScroll;
  const clearLogs = sseResult.clearLogs;

  // 从 run.tasks 构建 taskStatuses
  const taskStatuses = useMemo<Record<string, TaskStatus>>(() => {
    if (!run?.tasks) return {};
    const map: Record<string, TaskStatus> = {};
    for (const t of run.tasks) {
      map[t.task_name] = t.status;
    }
    return map;
  }, [run?.tasks]);

  // 进度与耗时
  const progress = useMemo(() => calcProgress(run), [run]);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!isLive) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [isLive]);
  const durationMs = useMemo(() => {
    if (!run?.started_at) return null;
    const start = new Date(run.started_at).getTime();
    const end = run.finished_at ? new Date(run.finished_at).getTime() : now;
    return Math.max(0, end - start);
  }, [run?.started_at, run?.finished_at, now]);

  const handleCancel = async () => {
    if (!id) return;
    try {
      await cancelRun.mutateAsync(id);
      message.success('已取消运行');
    } catch {
      message.error('取消失败');
    }
  };

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['run', id] });
    refetchLogs();
  };

  const handleCopyLogs = async () => {
    if (logs.length === 0) {
      message.warning('暂无日志可复制');
      return;
    }
    const text = logs.map((l) => (l.taskName ? `[${l.taskName}] ${l.content}` : l.content)).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      message.success(`已复制 ${logs.length} 行日志`);
    } catch {
      message.error('复制失败，请检查浏览器权限');
    }
  };

  if (runLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spin size="large" />
      </div>
    );
  }
  if (!run) return <div className="p-4">运行不存在</div>;

  const canCancel = run.status === 'running' || run.status === 'pending';

  return (
    <div className="flex flex-col h-full p-4 gap-3 bg-gray-50">
      {/* 顶部信息卡片 */}
      <div className="shrink-0 bg-white rounded-lg border border-gray-200 px-4 py-3 shadow-sm">
        <Breadcrumb
          items={[
            { title: <Link to="/runs">运行历史</Link> },
            { title: run.id.slice(0, 8) },
          ]}
          style={{ marginBottom: 8 }}
        />
        <div className="flex items-center justify-between flex-wrap gap-3">
          <Space size={12} wrap>
            <span style={{ fontSize: 18, fontWeight: 600 }}>{run.pipeline_name}</span>
            <StatusTag status={run.status} />
            {run.started_at && (
              <Tooltip title={`开始: ${new Date(run.started_at).toLocaleString('zh-CN')}${run.finished_at ? `\n结束: ${new Date(run.finished_at).toLocaleString('zh-CN')}` : ''}`}>
                <Tag icon={<Clock size={12} />} color="default" style={{ margin: 0 }}>
                  {formatDuration(durationMs ?? 0)}
                </Tag>
              </Tooltip>
            )}
            <Tooltip title="任务进度（成功+失败+跳过 / 总数）">
              <Tag color={progress.failed > 0 ? 'error' : progress.done === progress.total && progress.total > 0 ? 'success' : 'blue'} style={{ margin: 0 }}>
                进度 {progress.done}/{progress.total}
              </Tag>
            </Tooltip>
            {progress.running > 0 && (
              <Tag color="processing" style={{ margin: 0 }}>运行中 {progress.running}</Tag>
            )}
          </Space>
          <Space>
            <Tooltip title="手动刷新运行状态与日志">
              <Button
                size="small"
                icon={<RefreshCw size={14} className={logsFetching ? 'animate-spin' : ''} />}
                onClick={handleRefresh}
                loading={logsFetching}
              >
                刷新
              </Button>
            </Tooltip>
            <Tooltip title="复制全部日志到剪贴板">
              <Button size="small" icon={<Copy size={14} />} onClick={handleCopyLogs}>
                复制日志
              </Button>
            </Tooltip>
            <Button
              size="small"
              icon={<ListTree size={14} />}
              onClick={() => setTreeCollapsed((v) => !v)}
            >
              {treeCollapsed ? '显示任务树' : '隐藏任务树'}
            </Button>
            {canCancel && (
              <Popconfirm title="确认取消运行？" onConfirm={handleCancel}>
                <Button danger size="small" icon={<XCircle size={14} />} loading={cancelRun.isPending}>
                  取消运行
                </Button>
              </Popconfirm>
            )}
          </Space>
        </div>
      </div>

      {/* 主内容区：树 + 日志（可拖拽调整） */}
      <div className="flex flex-1 min-h-0">
        {treeCollapsed ? (
          // 树隐藏时，日志占满
          <div className="flex-1 min-h-0 rounded-lg overflow-hidden border border-gray-200 shadow-sm">
            <LogViewer
              logs={logs}
              connected={connected}
              autoScroll={autoScroll}
              onAutoScrollChange={setAutoScroll}
              onClear={clearLogs}
              selectedTaskId={selectedTaskId}
              onClearTaskFilter={() => setSelectedTaskId(null)}
            />
          </div>
        ) : (
          <Splitter
            className="flex-1 min-h-0"
            style={{ borderRadius: 8, overflow: 'hidden' }}
          >
            <Splitter.Panel
              defaultSize={240}
              min={180}
              max={420}
              className="bg-white border border-gray-200 shadow-sm rounded-lg overflow-hidden"
            >
              {pipeline ? (
                <TaskTree
                  pipeline={pipeline}
                  taskStatuses={taskStatuses}
                  selectedTaskId={selectedTaskId ?? undefined}
                  onSelect={setSelectedTaskId}
                />
              ) : (
                <div className="p-3 text-gray-400 text-sm">加载中…</div>
              )}
            </Splitter.Panel>
            <Splitter.Panel className="min-w-0">
              <div className="h-full rounded-lg overflow-hidden border border-gray-200 shadow-sm">
                <LogViewer
                  logs={logs}
                  connected={connected}
                  autoScroll={autoScroll}
                  onAutoScrollChange={setAutoScroll}
                  onClear={clearLogs}
                  selectedTaskId={selectedTaskId}
                  onClearTaskFilter={() => setSelectedTaskId(null)}
                />
              </div>
            </Splitter.Panel>
          </Splitter>
        )}
      </div>
    </div>
  );
}
