import { useMemo, useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Breadcrumb, Button, Space, Spin, message, Popconfirm, Splitter, Tooltip, Tag, Progress, Alert } from 'antd';
import { XCircle, ListTree, RefreshCw, Copy, Clock, CheckCircle2, AlertCircle, Loader2, Bug } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useRun, useCancelRun, useRunConsole, usePipelineSnapshot, useRetryVersions } from '@/api/runs';
import StatusTag from '@/components/StatusTag';
import LogViewer from './LogViewer';
import TaskTree from './TaskTree';
import RetryModal from './RetryModal';
import RetryVersionsDrawer from './RetryVersionsDrawer';
import { useSSELogs } from './hooks/useSSELogs';
import type { RunResponse, TaskStatus, TaskYAML } from '@/types';
import type { LogEntry } from './hooks/useSSELogs';

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

/** 终态任务状态集合 */
const TERMINAL_TASK_STATUS: Record<string, boolean> = {
  success: true, failed: true, skipped: true, cancelled: true,
};

/**
 * 将 SSE 推送的任务状态合并到 run 数据中。
 * Issue #61: useRun 每 3s refetch 会覆盖 queryClient 缓存中的 SSE 更新，
 * 因此在组件层用 useMemo 重新合并，确保 UI 始终反映最新状态。
 * 防护：服务端已是终态时不回退到非终态的 SSE 状态（SSE 断连重连期间可能过期）。
 */
function mergeTaskStatuses(run: RunResponse | undefined, statusMap: Record<string, TaskStatus>): RunResponse | undefined {
  if (!run || !statusMap || !Object.keys(statusMap).length) return run;
  let changed = false;
  const tasks = run.tasks.map((t) => {
    const newStatus = statusMap[t.task_name];
    if (!newStatus || newStatus === t.status) return t;
    if (TERMINAL_TASK_STATUS[t.status] && !TERMINAL_TASK_STATUS[newStatus]) return t;
    changed = true;
    return { ...t, status: newStatus };
  });
  return changed ? { ...run, tasks } : run;
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

function parseUTC(s: string): number {
  return new Date(s.endsWith('Z') || s.includes('+') ? s : s + 'Z').getTime();
}

/** 运行详情页面 */
export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: rawRun, isLoading: runLoading } = useRun(id);
  // 历史运行必须用执行时的快照，禁止回退到当前 pipeline 文件
  // （否则更新 pipeline 文件会影响历史数据的结构树展示 — Issue #57）
  const { data: snapshotPipeline, isLoading: snapshotLoading, error: snapshotError } = usePipelineSnapshot(id);
  const pipeline = snapshotPipeline;
  const cancelRun = useCancelRun();
  const queryClient = useQueryClient();

  const [treeCollapsed, setTreeCollapsed] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [debugVisible, setDebugVisible] = useState(false);

  // Issue #72: 右键重试相关状态
  const [retryTaskName, setRetryTaskName] = useState<string | null>(null);
  const [versionsTaskName, setVersionsTaskName] = useState<string | null>(null);

  // Issue #72: 拉取重试版本数据（用于显示重试数徽标 + 版本管理）
  const { data: retryVersions } = useRetryVersions(id);

  // Issue #72: 构建各任务的重试版本数映射（排除 v0 原始版本，只计重试次数）
  const retryCounts = useMemo(() => {
    if (!retryVersions?.task_retries) return {};
    const map: Record<string, number> = {};
    for (const [taskName, retries] of Object.entries(retryVersions.task_retries)) {
      if (retries) {
        const retryCount = retries.filter((r) => r.retry_version > 0).length;
        if (retryCount > 0) map[taskName] = retryCount;
      }
    }
    return map;
  }, [retryVersions]);

  // Issue #72: 从快照中查找任务定义（用于获取原始命令）
  const findTaskDef = useMemo(() => {
    return (taskId: string): TaskYAML | undefined => {
      if (!pipeline) return undefined;
      // taskId 格式为 "subpipeline.task"
      const dotIdx = taskId.indexOf('.');
      if (dotIdx < 0) {
        return pipeline.tasks?.find((t) => t.name === taskId);
      }
      const subName = taskId.slice(0, dotIdx);
      const taskName = taskId.slice(dotIdx + 1);
      const sub = pipeline.pipelines?.find((s) => s.name === subName);
      return sub?.tasks.find((t) => t.name === taskName);
    };
  }, [pipeline]);

  // SSE 日志（始终连接 — running 时实时推送，completed 时一次全推完 done）
  const sseResult = useSSELogs(id);

  // 日志：SSE 直接提供，无 SSE/REST 切换
  const baseLogs = sseResult.logs;

  // Issue #61: 在组件层合并 SSE 状态，避免 useRun 3s refetch 覆盖 SSE 实时更新
  // （原先的 useEffect 写 queryClient 缓存会被下一次 refetch 覆盖，导致状态不更新）
  const run = useMemo(
    () => mergeTaskStatuses(rawRun, sseResult.taskStatusMap ?? {}),
    [rawRun, sseResult.taskStatusMap],
  );

  const isLive = run?.status === 'running' || run?.status === 'pending';

  // Debug 模式：拉取 console.log 并合并 phase 日志
  const { data: consoleData } = useRunConsole(debugVisible ? id : undefined, 500);

  // 解析 phase groups 并转为 LogEntry
  const phaseLogEntries = useMemo(() => {
    if (!debugVisible || !consoleData?.content) return [];
    const entries: LogEntry[] = [];
    const lines = consoleData.content.split('\n');
    let currentPhase = '';
    for (const line of lines) {
      const phaseMatch = line.match(/^\[(PIPELINE:SETUP|PIPELINE:TEARDOWN|SUB:([^:]+):SETUP|SUB:([^:]+):TEARDOWN|TASK:([^:]+):SETUP|TASK:([^:]+):TEARDOWN)\]/);
      if (phaseMatch) {
        const tag = phaseMatch[1];
        if (tag.startsWith('TASK:')) {
          const rest = tag.slice(5);
          const lastColon = rest.lastIndexOf(':');
          currentPhase = rest.slice(0, lastColon);
        } else if (tag.startsWith('SUB:')) {
          const parts = tag.split(':');
          currentPhase = parts[1];
        } else {
          currentPhase = 'pipeline';
        }
        continue;
      }
      if (line.trim()) {
        entries.push({ taskName: `__phase__${currentPhase}`, content: line, timestamp: 0, seq: 0 });
      }
    }
    return entries;
  }, [debugVisible, consoleData?.content]);

  // 合并日志：debug 模式下 phase 日志在前，任务日志在后
  const logs = useMemo(() => {
    if (!debugVisible || phaseLogEntries.length === 0) return baseLogs;
    return [...phaseLogEntries, ...baseLogs];
  }, [baseLogs, debugVisible, phaseLogEntries]);

  const connected = sseResult.connected;
  const autoScroll = sseResult.autoScroll;
  const setAutoScroll = sseResult.setAutoScroll;
  const clearLogs = sseResult.clearLogs;

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
    const start = parseUTC(run.started_at);
    const end = run.finished_at ? parseUTC(run.finished_at) : now;
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
            { title: <Tooltip title={run.id}>{run.display_name || run.id.slice(0, 8)}</Tooltip> },
          ]}
          style={{ marginBottom: 8 }}
        />
        <div className="flex items-center justify-between flex-wrap gap-3">
          <Space size={12} wrap>
            <span style={{ fontSize: 18, fontWeight: 600 }}>{run.pipeline_name}</span>
            <StatusTag status={run.status} error={run.error} />
            <ProgressBadge
              done={progress.done}
              total={progress.total}
              failed={progress.failed}
              running={progress.running}
            />
            {progress.running > 0 && (
              <Tag color="processing" style={{ margin: 0, padding: '2px 8px', display: 'inline-flex', alignItems: 'center', gap: 4, lineHeight: '20px', height: 24 }}>运行中 {progress.running}</Tag>
            )}
          </Space>
          <Space>
            {run.started_at && (
              <Tooltip title={`开始: ${new Date(run.started_at).toLocaleString('zh-CN')}${run.finished_at ? `\n结束: ${new Date(run.finished_at).toLocaleString('zh-CN')}` : ''}`}>
                <Tag icon={<Clock size={12} />} color="default" style={{ margin: 0, padding: '2px 8px', display: 'inline-flex', alignItems: 'center', gap: 4, lineHeight: '20px', height: 24 }}>
                  {formatDuration(durationMs ?? 0)}
                </Tag>
              </Tooltip>
            )}
            <Tooltip title="手动刷新运行状态">
              <Button
                size="small"
                icon={<RefreshCw size={14} />}
                onClick={handleRefresh}
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
            <Button
              size="small"
              icon={<Bug size={14} />}
              onClick={() => setDebugVisible((v) => !v)}
              type={debugVisible ? 'primary' : 'default'}
            >
              {debugVisible ? '关闭 Debug' : 'Debug'}
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

      {/* 失败原因横幅 */}
      {run.error && (run.status === 'failed' || run.status === 'partial') && (
        <Alert
          type="error"
          showIcon
          icon={<AlertCircle size={16} />}
          message="失败原因"
          description={run.error}
          style={{ borderRadius: 8 }}
          closable
        />
      )}

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
              failedCount={progress.failed}
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
                  taskRuns={run?.tasks}
                  selectedTaskId={selectedTaskId ?? undefined}
                  onSelect={setSelectedTaskId}
                  debugVisible={debugVisible}
                  runId={id}
                  isLive={isLive}
                  taskStatusMap={sseResult.taskStatusMap}
                  onRetry={setRetryTaskName}
                  onShowVersions={setVersionsTaskName}
                  retryCounts={retryCounts}
                />
              ) : snapshotLoading ? (
                <div className="p-3 text-gray-400 text-sm">加载历史快照中…</div>
              ) : snapshotError ? (
                <div className="p-3 text-orange-500 text-sm">历史快照加载失败</div>
              ) : (
                <div className="p-3 text-gray-400 text-sm">暂无快照</div>
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
                  failedCount={progress.failed}
                />
              </div>
            </Splitter.Panel>
          </Splitter>
        )}
      </div>

      {/* Issue #72: 重试弹窗 */}
      {retryTaskName && id && (
        <RetryModal
          open={retryTaskName !== null}
          runId={id}
          taskName={retryTaskName}
          taskStatus={run.tasks.find((t) => t.task_name === retryTaskName)?.status}
          taskCommand={findTaskDef(retryTaskName)?.command ?? findTaskDef(retryTaskName)?.commands?.join('\n') ?? undefined}
          onClose={() => setRetryTaskName(null)}
        />
      )}

      {/* Issue #72: 重试版本管理抽屉 */}
      {versionsTaskName && id && (
        <RetryVersionsDrawer
          open={versionsTaskName !== null}
          runId={id}
          taskName={versionsTaskName}
          onClose={() => setVersionsTaskName(null)}
        />
      )}
    </div>
  );
}

/** 任务进度徽标：mini 圆形 Progress + 文字 + 状态图标 */
function ProgressBadge({ done, total, failed, running }: { done: number; total: number; failed: number; running: number }) {
  const safeTotal = Math.max(total, 1);
  const percent = Math.min(100, Math.round((done / safeTotal) * 100));
  const isFailed = failed > 0;
  const isDone = total > 0 && done === total;

  // 颜色与状态：失败红 / 完成绿 / 进行中蓝
  const color = isFailed ? '#ef4444' : isDone ? '#10b981' : '#3b82f6';
  const status: 'success' | 'exception' | 'active' | 'normal' = isFailed
    ? 'exception'
    : isDone
      ? 'success'
      : running > 0
        ? 'active'
        : 'normal';

  // 失败优先显示失败数，否则显示完成比例
  const label = isFailed ? `${failed} 失败` : `${done}/${total}`;

  // 提示文字
  const tooltipText = isFailed
    ? `失败 ${failed} / 总数 ${total}（已处理 ${done}）`
    : isDone
      ? `已完成 ${done} / ${total}`
      : `进行中：已处理 ${done} / ${total}（${percent}%）`;

  return (
    <Tooltip title={tooltipText}>
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '2px 8px 2px 6px',
          margin: 0,
          height: 24,
          lineHeight: '20px',
          fontSize: 12,
          background: '#fff',
          border: `1px solid ${color}`,
          borderRadius: 12,
          color: isFailed ? '#b91c1c' : isDone ? '#047857' : '#1d4ed8',
          whiteSpace: 'nowrap',
        }}
      >
        <Progress
          type="circle"
          percent={isDone ? 100 : percent}
          size={16}
          strokeWidth={14}
          showInfo={false}
          strokeColor={color}
          status={status === 'normal' ? 'normal' : status}
        />
        <span style={{ fontWeight: 500 }}>{label}</span>
        {running > 0 ? (
          <Loader2 size={11} color={color} className="animate-spin" />
        ) : isFailed ? (
          <AlertCircle size={11} color={color} />
        ) : isDone ? (
          <CheckCircle2 size={11} color={color} />
        ) : null}
      </div>
    </Tooltip>
  );
}
