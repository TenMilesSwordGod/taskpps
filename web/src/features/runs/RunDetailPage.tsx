import { useMemo, useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Breadcrumb, Button, Space, Spin, message, Popconfirm, Splitter, Tooltip, Tag, Progress } from 'antd';
import { XCircle, ListTree, RefreshCw, Copy, Clock, CheckCircle2, AlertCircle, Loader2, Bug } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useRun, useCancelRun, useRunConsole } from '@/api/runs';
import { usePipeline } from '@/api/pipelines';
import StatusTag from '@/components/StatusTag';
import LogViewer from './LogViewer';
import TaskTree from './TaskTree';
import { useSSELogs } from './hooks/useSSELogs';
import type { RunResponse } from '@/types';
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
  const [debugVisible, setDebugVisible] = useState(false);

  const isLive = run?.status === 'running' || run?.status === 'pending';

  // SSE 日志（始终连接 — running 时实时推送，completed 时一次全推完 done）
  const sseResult = useSSELogs(id);

  // 日志：SSE 直接提供，无 SSE/REST 切换
  const baseLogs = sseResult.logs;

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
                <Tag icon={<Clock size={12} />} color="default" style={{ margin: 0, padding: '2px 8px', display: 'inline-flex', alignItems: 'center', gap: 4, lineHeight: '20px', height: 24 }}>
                  {formatDuration(durationMs ?? 0)}
                </Tag>
              </Tooltip>
            )}
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
              runId={id}
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
                  failedCount={progress.failed}
                  runId={id}
                />
              </div>
            </Splitter.Panel>
          </Splitter>
        )}
      </div>
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
