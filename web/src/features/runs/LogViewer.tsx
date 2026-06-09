import { useState, useMemo, useRef, useEffect } from 'react';
import { Select, Input, Switch, Button, Empty, Tag, Tooltip, Space } from 'antd';
import { Trash2, Filter, Layers, Download, AlertCircle, AlertTriangle, Info, Bug, Terminal } from 'lucide-react';
import type { LogEntry } from './hooks/useSSELogs';

interface LogViewerProps {
  logs: LogEntry[];
  connected: boolean;
  autoScroll: boolean;
  onAutoScrollChange: (v: boolean) => void;
  onClear: () => void;
  /** 外部选中的任务 ID（树形点击），用于过滤日志 */
  selectedTaskId?: string | null;
  /** 清除外部选择 */
  onClearTaskFilter?: () => void;
  /** 任务执行状态（用于显示 N failed 等） */
  failedCount?: number;
}

/** 任务名颜色映射 */
const TASK_COLORS = [
  '#60a5fa', '#34d399', '#fbbf24', '#f87171',
  '#a78bfa', '#fb923c', '#2dd4bf', '#f472b6',
];

function getTaskColor(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return TASK_COLORS[Math.abs(hash) % TASK_COLORS.length];
}

type LogLevel = 'error' | 'warn' | 'info' | 'debug' | 'unknown';

const LEVEL_PATTERNS: Array<{ level: LogLevel; regex: RegExp }> = [
  { level: 'error', regex: /^(?:\[ERROR\]|\[ERR\]|ERROR:|\[FATAL\]|Traceback \(most recent call last\)[:\s]|\bError:|\bException:)/i },
  { level: 'warn', regex: /^(?:\[WARN(?:ING)?\]|WARN(?:ING)?:|\[WARN\])/i },
  { level: 'debug', regex: /^(?:\[DEBUG\]|DEBUG:)/i },
  { level: 'info', regex: /^(?:\[INFO\]|INFO:)/i },
];

function detectLevel(content: string): LogLevel {
  for (const { level, regex } of LEVEL_PATTERNS) {
    if (regex.test(content)) return level;
  }
  return 'unknown';
}

function isStderr(content: string): boolean {
  return /^\[STDERR\]/.test(content);
}

const LEVEL_STYLE: Record<LogLevel, { color: string; bg: string; icon: typeof Info; label: string }> = {
  error: { color: '#fca5a5', bg: 'rgba(239, 68, 68, 0.12)', icon: AlertCircle, label: 'ERROR' },
  warn: { color: '#fcd34d', bg: 'rgba(245, 158, 11, 0.10)', icon: AlertTriangle, label: 'WARN' },
  info: { color: '#93c5fd', bg: 'transparent', icon: Info, label: 'INFO' },
  debug: { color: '#9ca3af', bg: 'transparent', icon: Bug, label: 'DEBUG' },
  unknown: { color: '#d1d5db', bg: 'transparent', icon: Terminal, label: 'LOG' },
};

const ALL_LEVELS: LogLevel[] = ['error', 'warn', 'info', 'debug'];

/** SSE 日志查看器 */
export default function LogViewer({
  logs,
  connected,
  autoScroll,
  onAutoScrollChange,
  onClear,
  selectedTaskId,
  onClearTaskFilter,
  failedCount = 0,
}: LogViewerProps) {
  const [taskFilter, setTaskFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
  const [levelFilter, setLevelFilter] = useState<LogLevel[]>([...ALL_LEVELS]);
  const scrollRef = useRef<HTMLDivElement>(null);
  // 跟踪是否用户已向上滚动，暂停自动滚动
  const stickyToBottomRef = useRef(true);

  // 提取唯一任务名（去重）
  const taskNames = useMemo(
    () => [...new Set(logs.map((l) => l.taskName).filter(Boolean))],
    [logs],
  );

  // 当前生效的过滤（外部选中优先）
  const effectiveFilter = selectedTaskId ?? taskFilter;

  // 过滤日志
  const filtered = useMemo(() => {
    let result = logs;
    if (effectiveFilter) result = result.filter((l) => l.taskName === effectiveFilter);
    if (searchText) result = result.filter((l) => l.content.includes(searchText));
    if (levelFilter.length < ALL_LEVELS.length) {
      result = result.filter((l) => levelFilter.includes(detectLevel(l.content)));
    }
    return result;
  }, [logs, effectiveFilter, searchText, levelFilter]);

  // 统计各级别数量
  const levelStats = useMemo(() => {
    const stats: Record<LogLevel, number> = { error: 0, warn: 0, info: 0, debug: 0, unknown: 0 };
    const scoped = effectiveFilter ? logs.filter((l) => l.taskName === effectiveFilter) : logs;
    for (const l of scoped) stats[detectLevel(l.content)]++;
    return stats;
  }, [logs, effectiveFilter]);

  // 自动滚动到底部
  useEffect(() => {
    if (!autoScroll || filtered.length === 0) return;
    const el = scrollRef.current;
    if (!el) return;
    if (stickyToBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [filtered.length, filtered, autoScroll]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickyToBottomRef.current = distanceToBottom < 24;
  };

  useEffect(() => {
    if (filtered.length === 0) stickyToBottomRef.current = true;
  }, [filtered.length]);

  // 导出当前过滤后日志为文件
  const handleExport = () => {
    const text = filtered
      .map((l) => {
        const ts = new Date(l.timestamp).toISOString();
        return l.taskName ? `${ts} [${l.taskName}] ${l.content}` : `${ts} ${l.content}`;
      })
      .join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `run-logs-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 工具栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          background: '#1f2937',
          borderBottom: '1px solid #374151',
          flexWrap: 'wrap',
        }}
      >
        {/* 任务过滤 - 树形选中标签优先展示 */}
        {selectedTaskId ? (
          <Tag
            color="default"
            closable
            onClose={onClearTaskFilter}
            icon={<Filter size={12} style={{ color: '#6b7280' }} />}
            style={{
              margin: 0, padding: '2px 8px', display: 'inline-flex',
              alignItems: 'center', gap: 4, lineHeight: '20px', height: 24,
              background: '#fff', borderColor: '#d1d5db',
            }}
          >
            <span style={{ fontFamily: 'monospace' }}>{selectedTaskId}</span>
          </Tag>
        ) : (
          <Select
            allowClear
            placeholder="按任务过滤"
            value={taskFilter}
            onChange={setTaskFilter}
            style={{ width: 180 }}
            size="small"
            options={taskNames.map((n) => ({ label: n, value: n }))}
          />
        )}

        {/* Level 过滤 */}
        <Select
          mode="multiple"
          size="small"
          value={levelFilter}
          onChange={setLevelFilter}
          style={{ minWidth: 220 }}
          maxTagCount="responsive"
          placeholder="按级别过滤"
          options={ALL_LEVELS.map((lv) => {
            const s = LEVEL_STYLE[lv];
            const count = levelStats[lv];
            return { label: `${s.label} (${count})`, value: lv };
          })}
        />

        <Input.Search
          placeholder="搜索日志内容"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={setSearchText}
          style={{ width: 200 }}
          size="small"
          allowClear
        />
        <Switch
          size="small"
          checked={autoScroll}
          onChange={onAutoScrollChange}
          checkedChildren="自动滚动"
          unCheckedChildren="暂停"
        />
        <Button size="small" icon={<Trash2 size={14} />} onClick={onClear}>
          清空
        </Button>
        <Button size="small" icon={<Download size={14} />} onClick={handleExport} disabled={filtered.length === 0}>
          导出
        </Button>

        <div style={{ flex: 1 }} />

        {failedCount > 0 && (
          <Tag color="error" style={{ margin: 0, padding: '2px 8px', display: 'inline-flex', alignItems: 'center', gap: 4, lineHeight: '20px', height: 24 }}>
            <AlertCircle size={12} /> {failedCount} failed
          </Tag>
        )}

        <Tag
          style={{
            margin: 0, padding: '2px 8px', display: 'inline-flex',
            alignItems: 'center', gap: 4, lineHeight: '20px', height: 24,
          }}
        >
          <Layers size={12} /> {filtered.length} / {logs.length} 行
        </Tag>

        {connected && (
          <span style={{ color: '#34d399', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            ● 已连接
          </span>
        )}
      </div>

      {/* 日志内容 */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{ flex: 1, background: '#111827', minHeight: 120, overflow: 'auto' }}
      >
        {logs.length === 0 ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span style={{ color: '#6b7280' }}>暂无日志输出</span>} />
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span style={{ color: '#6b7280' }}>无匹配日志</span>} />
          </div>
        ) : (
          <div style={{ padding: '6px 0' }}>
            {filtered.map((log, i) => {
              const level = detectLevel(log.content);
              const stderr = isStderr(log.content);
              const ls = LEVEL_STYLE[level];
              const showBg = level === 'error' || stderr;
              return (
                <div
                  key={`${i}-${log.taskName}-${log.timestamp}`}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'auto auto 1fr',
                    columnGap: 8,
                    padding: '1px 12px',
                    fontSize: 13,
                    fontFamily: 'monospace',
                    lineHeight: '20px',
                    background: showBg ? ls.bg : 'transparent',
                    borderLeft: level === 'error' ? '3px solid #ef4444' : stderr ? '3px solid #f59e0b' : '3px solid transparent',
                  }}
                >
                  {/* level badge */}
                  <Tooltip title={stderr ? 'STDERR' : ls.label}>
                    <span style={{ color: ls.color, fontWeight: 600, minWidth: 48, fontSize: 11, paddingTop: 2 }}>
                      {stderr ? 'ERR ' : ls.label}
                    </span>
                  </Tooltip>
                  {/* task name */}
                  {log.taskName ? (
                    <span
                      style={{
                        color: getTaskColor(log.taskName),
                        fontWeight: 500,
                        minWidth: 0,
                      }}
                    >
                      [{log.taskName}]
                    </span>
                  ) : (
                    <span />
                  )}
                  {/* content */}
                  <span style={{ color: '#d1d5db', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {log.content}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
