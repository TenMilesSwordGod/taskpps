import { useState, useEffect, useRef, useCallback } from 'react';

export interface LogEntry {
  taskName: string;
  content: string;
  timestamp: number;
}

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
      const colonIndex = data.indexOf(': ');
      const taskName = colonIndex > 0 ? data.substring(0, colonIndex) : '';
      const raw = colonIndex > 0 ? data.substring(colonIndex + 2) : data;

      // 单条 SSE 事件可能含多行（批量推送），按行拆分并过滤空行
      const lines = raw.split(/\r\n|\r|\n/).filter((l) => l.length > 0);
      if (lines.length === 0) return;

      setLogs((prev) => [
        ...prev,
        ...lines.map((content) => ({ taskName, content, timestamp: Date.now() })),
      ]);
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
