import { useState, useMemo, useRef, useEffect, useCallback, Fragment } from 'react';
import { Select, Input, Button, Empty, Tag, Tooltip } from 'antd';
import { Trash2, Filter, Layers, Download, Copy, AlertCircle, AlertTriangle, Info, Bug, Terminal, ArrowDownToLine } from 'lucide-react';
import { VariableSizeList as List } from 'react-window';
import type { LogEntry } from './hooks/useSSELogs';

interface LogViewerProps {
  logs: LogEntry[];
  connected: boolean;
  onClear: () => void;
  selectedTaskId?: string | null;
  onClearTaskFilter?: () => void;
  failedCount?: number;
  onCopyLogs?: () => void;
}

const TASK_COLORS = [
  '#60a5fa', '#34d399', '#fbbf24', '#f87171',
  '#a78bfa', '#fb923c', '#2dd4bf', '#f472b6',
  '#818cf8', '#4ade80', '#facc15', '#fb7185',
  '#c084fc', '#22d3ee', '#a3e635', '#e879f9',
];

type LogLevel = 'error' | 'warn' | 'info' | 'debug' | 'unknown';

interface FilteredLogEntry extends LogEntry {
  level: LogLevel;
  stderr: boolean;
}

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
const ROW_HEIGHT = 20;

export default function LogViewer({
  logs,
  connected,
  onClear,
  selectedTaskId,
  onClearTaskFilter,
  failedCount = 0,
  onCopyLogs,
}: LogViewerProps) {
  const [taskFilter, setTaskFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
  const [levelFilter, setLevelFilter] = useState<LogLevel[]>([...ALL_LEVELS]);
  const [showTaskNames, setShowTaskNames] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<List>(null);
  const outerRef = useRef<HTMLDivElement>(null);
  const [containerHeight, setContainerHeight] = useState(400);
  const [containerWidth, setContainerWidth] = useState(800);
  const stickyToBottomRef = useRef(true);
  const prevSelectedTaskIdRef = useRef<string | null | undefined>(undefined);
  const taskNames = useMemo(
    () => [...new Set(logs.map((l) => l.taskName).filter(Boolean))],
    [logs],
  );

  // Issue #71: 按任务首次出现顺序分配颜色，避免 hash 碰撞导致相邻任务同色
  const taskColorMap = useMemo(() => {
    const map = new Map<string, string>();
    taskNames.forEach((name, i) => {
      map.set(name, TASK_COLORS[i % TASK_COLORS.length]);
    });
    return map;
  }, [taskNames]);

  const effectiveFilter = selectedTaskId ?? taskFilter;

  const phaseFilter = useMemo(() => {
    if (!effectiveFilter || !effectiveFilter.startsWith('__phase__')) return null;
    const parts = effectiveFilter.split('__');
    if (parts.length >= 4) return `__phase__${parts[2]}`;
    return effectiveFilter;
  }, [effectiveFilter]);

  const filtered = useMemo(() => {
    let result: FilteredLogEntry[] = logs.map((l) => ({
      ...l,
      level: detectLevel(l.content),
      stderr: isStderr(l.content),
    }));

    if (phaseFilter) {
      result = result.filter((l) => l.taskName === phaseFilter);
    } else if (effectiveFilter) {
      result = result.filter((l) => l.taskName === effectiveFilter);
    }
    if (searchText) result = result.filter((l) => l.content.includes(searchText));
    if (levelFilter.length < ALL_LEVELS.length) {
      result = result.filter((l) => levelFilter.includes(l.level));
    }
    return result;
  }, [logs, effectiveFilter, phaseFilter, searchText, levelFilter]);

  const levelStats = useMemo(() => {
    const stats: Record<LogLevel, number> = { error: 0, warn: 0, info: 0, debug: 0, unknown: 0 };
    const scoped = effectiveFilter ? logs.map((l) => ({ ...l, level: detectLevel(l.content) })) : logs;
    for (const l of scoped) {
      const lv = 'level' in l ? (l as FilteredLogEntry).level : detectLevel((l as LogEntry).content);
      stats[lv]++;
    }
    return stats;
  }, [logs, effectiveFilter]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height);
        setContainerWidth(entry.contentRect.width);
      }
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const CHARS_PER_LINE = useMemo(() => {
    // 13px monospace ≈ 7.8px per char, subtract ~100px for level badge + task name
    return Math.max(40, Math.floor((containerWidth - 100) / 7.8));
  }, [containerWidth]);

  const getItemSize = useCallback(
    (index: number) => {
      const content = filtered[index]?.content || '';
      const lines = content.split('\n');
      let totalLines = lines.length;
      for (const line of lines) {
        if (line.length > CHARS_PER_LINE) {
          totalLines += Math.ceil(line.length / CHARS_PER_LINE) - 1;
        }
      }
      return Math.max(ROW_HEIGHT, totalLines * ROW_HEIGHT);
    },
    [filtered, CHARS_PER_LINE],
  );

  // 重置大小缓存当过滤条件变化
  useEffect(() => {
    listRef.current?.resetAfterIndex(0);
  }, [filtered]);

  // Jenkins 式自动跟随：用 onScroll 检测用户滚动位置，
  // 避免 onItemsRendered 在 render 阶段同步触发导致的新日志竞态（旧代码 bug）
  const handleScroll = useCallback(({ scrollOffset, scrollUpdateWasRequested }: { scrollOffset: number; scrollUpdateWasRequested: boolean }) => {
    if (!outerRef.current || scrollUpdateWasRequested) return;
    const { scrollHeight, clientHeight } = outerRef.current;
    // 距离底部 < 50px 视为"在底部"，恢复自动跟随
    stickyToBottomRef.current = scrollHeight - clientHeight - scrollOffset < 50;
  }, []);

  // 新日志到来时自动滚动到底部（仅在用户处于底部时）
  useEffect(() => {
    if (filtered.length === 0 || !stickyToBottomRef.current) return;
    listRef.current?.scrollToItem(filtered.length - 1, 'end');
  }, [filtered.length]);

  // 日志被清空时重置为"在底部"状态
  useEffect(() => {
    if (filtered.length === 0) stickyToBottomRef.current = true;
  }, [filtered.length]);

  useEffect(() => {
    const prev = prevSelectedTaskIdRef.current;
    prevSelectedTaskIdRef.current = selectedTaskId;
    if (prev == null || selectedTaskId != null) return;
    const target = prev;
    requestAnimationFrame(() => {
      const idx = filtered.findIndex((l) => l.taskName === target);
      if (idx >= 0) {
        listRef.current?.scrollToItem(idx, 'center');
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTaskId]);

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

  const LogRow = useCallback(
    ({ index, style }: { index: number; style: React.CSSProperties }) => {
      const log = filtered[index];
      const ls = LEVEL_STYLE[log.level];
      const showBg = log.level === 'error' || log.stderr;
      return (
        <div
          style={{
            ...style,
            display: 'grid',
            gridTemplateColumns: showTaskNames ? 'auto auto 1fr' : 'auto 1fr',
            columnGap: 8,
            padding: '1px 12px',
            fontSize: 13,
            fontFamily: 'monospace',
            lineHeight: `${ROW_HEIGHT}px`,
            background: showBg ? ls.bg : 'transparent',
            borderLeft: log.level === 'error' ? '3px solid #ef4444' : log.stderr ? '3px solid #f59e0b' : '3px solid transparent',
          }}
          data-task-name={log.taskName || ''}
        >
          <Tooltip title={log.stderr ? 'STDERR' : ls.label}>
            <span style={{ color: ls.color, fontWeight: 600, minWidth: 48, fontSize: 11, paddingTop: 2 }}>
              {log.stderr ? 'ERR ' : ls.label}
            </span>
          </Tooltip>
          {showTaskNames && (
            log.taskName ? (
              <span style={{ color: taskColorMap.get(log.taskName) || '#d1d5db', fontWeight: 500, minWidth: 0 }}>
                [{log.taskName}]
              </span>
            ) : (
              <span />
            )
          )}
          <span style={{ color: '#d1d5db', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {log.content}
          </span>
        </div>
      );
    },
    [filtered, showTaskNames, taskColorMap],
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
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
            <span style={{ fontFamily: 'monospace' }}>{selectedTaskId.startsWith('__phase__') ? selectedTaskId.split('__').slice(2).join(' → ') : selectedTaskId}</span>
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
        <Button size="small" icon={<Trash2 size={14} />} onClick={onClear}>
          清空
        </Button>
        {onCopyLogs && (
          <Button size="small" icon={<Copy size={14} />} onClick={onCopyLogs} disabled={logs.length === 0}>
            复制
          </Button>
        )}
        <Button size="small" icon={<Download size={14} />} onClick={handleExport} disabled={filtered.length === 0}>
          导出
        </Button>
        <Button
          size="small"
          type={showTaskNames ? 'default' : 'text'}
          onClick={() => setShowTaskNames((v) => !v)}
          title={showTaskNames ? '隐藏任务名' : '显示任务名'}
        >
          {showTaskNames ? '≡ 任务名' : '≡'}
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

      <div
        ref={containerRef}
        style={{ flex: 1, background: '#111827', minHeight: 120, overflow: 'hidden', position: 'relative' }}
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
          <Fragment>
            <List
              ref={listRef}
              outerRef={outerRef}
              height={containerHeight}
              itemCount={filtered.length}
              itemSize={getItemSize}
              width="100%"
              onScroll={handleScroll}
            >
              {LogRow}
            </List>
            {!stickyToBottomRef.current && filtered.length > 0 && (
              <div style={{ position: 'absolute', bottom: 16, right: 16, zIndex: 10 }}>
                <Button
                  type="primary"
                  icon={<ArrowDownToLine size={14} />}
                  onClick={() => {
                    stickyToBottomRef.current = true;
                    listRef.current?.scrollToItem(filtered.length - 1, 'end');
                  }}
                >
                  滚动到底部
                </Button>
              </div>
            )}
          </Fragment>
        )}
      </div>
    </div>
  );
}
