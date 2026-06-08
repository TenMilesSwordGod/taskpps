import { useState, useMemo, useRef, useEffect } from 'react';
import { Select, Input, Switch, Button, Empty, Tag } from 'antd';
import { Trash2, Filter, Layers } from 'lucide-react';
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

/** SSE 日志查看器 */
export default function LogViewer({
  logs,
  connected,
  autoScroll,
  onAutoScrollChange,
  onClear,
  selectedTaskId,
  onClearTaskFilter,
}: LogViewerProps) {
  const [taskFilter, setTaskFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
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
    return result;
  }, [logs, effectiveFilter, searchText]);

  // 自动滚动到底部
  useEffect(() => {
    if (!autoScroll || filtered.length === 0) return;
    const el = scrollRef.current;
    if (!el) return;
    // 仅在用户已处于（接近）底部时才自动滚动
    if (stickyToBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [filtered.length, filtered, autoScroll]);

  // 监听用户滚动，判断是否离开底部
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickyToBottomRef.current = distanceToBottom < 24;
  };

  // 用户清空后，底部跟踪状态重置
  useEffect(() => {
    if (filtered.length === 0) stickyToBottomRef.current = true;
  }, [filtered.length]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 工具栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: '#1f2937', borderBottom: '1px solid #374151', flexWrap: 'wrap' }}>
        {/* 任务过滤 - 树形选中标签优先展示 */}
        {selectedTaskId ? (
          <Tag
            color="purple"
            closable
            onClose={onClearTaskFilter}
            icon={<Filter size={12} />}
            style={{ margin: 0 }}
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
        <div style={{ flex: 1 }} />
        <Tag color="default" icon={<Layers size={12} />}>
          {filtered.length} / {logs.length} 行
        </Tag>
        {connected && (
          <span style={{ color: '#34d399', fontSize: 12 }}>● 已连接</span>
        )}
      </div>

      {/* 日志内容 - 多行折行渲染 */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{ flex: 1, background: '#111827', minHeight: 120, overflow: 'auto' }}
      >
        {logs.length === 0 ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={<span style={{ color: '#6b7280' }}>暂无日志输出</span>}
            />
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={<span style={{ color: '#6b7280' }}>无匹配日志</span>}
            />
          </div>
        ) : (
          <div style={{ padding: '6px 0' }}>
            {filtered.map((log, i) => (
              <div
                // 用 i + content 作 key，避免重复内容被复用
                key={`${i}-${log.taskName}-${log.timestamp}`}
                style={{
                  display: 'grid',
                  gridTemplateColumns: log.taskName ? 'auto 1fr' : '1fr',
                  columnGap: 8,
                  padding: '1px 12px',
                  fontSize: 13,
                  fontFamily: 'monospace',
                  lineHeight: '20px',
                }}
              >
                {log.taskName && (
                  <span
                    style={{
                      color: getTaskColor(log.taskName),
                      fontWeight: 500,
                    }}
                  >
                    [{log.taskName}]
                  </span>
                )}
                <span style={{ color: '#d1d5db', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {log.content}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
