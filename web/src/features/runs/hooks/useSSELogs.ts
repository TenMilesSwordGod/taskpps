import { useState, useEffect, useRef, useCallback } from 'react';

export interface LogEntry {
  /** 全局自增序列号，保证同毫秒内多条日志 key 唯一 */
  seq: number;
  taskName: string;
  content: string;
  timestamp: number;
}

/** 日志最大行数（DOM 性能保护） */
const MAX_LOG_LINES = 50000;

/** 全局日志序列号（模块级，避免 hook 重 mount 后 seq 回零导致冲突） */
let globalSeq = 0;

/** SSE 实时日志 hook */
export function useSSELogs(runId: string | undefined) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId) return;

    const es = new EventSource(`/api/runs/${runId}/logs?follow=true`);
    eventSourceRef.current = es;

    es.onopen = () => setConnected(true);

    es.addEventListener('log', (e) => {
      const data = e.data as string;
      if (!data) return;
      const colonIndex = data.indexOf(': ');
      const taskName = colonIndex > 0 ? data.substring(0, colonIndex) : '';
      const raw = colonIndex > 0 ? data.substring(colonIndex + 2) : data;

      // 按换行拆分，保留空行（日志空行有意义），去掉 \r
      const cleanRaw = raw.replace(/\r/g, '');
      const lines = cleanRaw.split('\n');
      // 仅去除 split 产生的末尾空元素，保留中间空行
      while (lines.length > 1 && lines[lines.length - 1] === '') {
        lines.pop();
      }
      if (lines.length === 0) return;

      setLogs((prev) => {
        const appended = lines.map((content) => ({
          seq: ++globalSeq,
          taskName,
          content,
          timestamp: Date.now(),
        }));
        // 上限保护：超过 MAX 时丢弃最早的 1/4，避免 DOM 节点无限增长
        const next = [...prev, ...appended];
        if (next.length > MAX_LOG_LINES) {
          return next.slice(next.length - Math.floor(MAX_LOG_LINES * 0.75));
        }
        return next;
      });
    });

    es.addEventListener('done', () => {
      setConnected(false);
      es.close();
    });

    es.onerror = () => {
      setConnected(false);
      es.close();
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [runId]);

  const clearLogs = useCallback(() => setLogs([]), []);

  return { logs, connected, autoScroll, setAutoScroll, clearLogs };
}
