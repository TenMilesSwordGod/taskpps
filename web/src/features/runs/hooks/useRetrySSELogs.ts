import { useState, useEffect, useRef, useCallback } from 'react';

export interface RetryLogEntry {
  seq: number;
  content: string;
  timestamp: number;
}

/** 日志最大行数（DOM 性能保护） */
const MAX_LOG_LINES = 50000;

/** 全局日志序列号（模块级，避免 hook 重 mount 后 seq 回零导致冲突） */
let retryGlobalSeq = 0;

/** SSE 重连基础延迟（ms），实际延迟 = base * 2^attempt，上限 10s */
const RECONNECT_BASE_DELAY = 1000;
const RECONNECT_MAX_DELAY = 10000;

/** 重试日志 SSE 实时 hook */
export function useRetrySSELogs(runId: string | undefined, retryId: string | undefined) {
  const [logs, setLogs] = useState<RetryLogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const runIdRef = useRef(runId);
  const retryIdRef = useRef(retryId);
  runIdRef.current = runId;
  retryIdRef.current = retryId;

  const connect = useCallback(() => {
    const currentRunId = runIdRef.current;
    const currentRetryId = retryIdRef.current;
    if (!currentRunId || !currentRetryId) return;

    // 清理旧连接
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const es = new EventSource(
      `/api/runs/${currentRunId}/retry/${currentRetryId}/logs?follow=true`,
    );
    eventSourceRef.current = es;

    es.onopen = () => {
      setConnected(true);
      reconnectAttemptRef.current = 0;
    };

    es.addEventListener('retry_log', (e) => {
      const data = e.data as string;
      if (!data) return;

      // 按换行拆分，保留空行，去掉 \r
      const cleanData = data.replace(/\r/g, '');
      const lines = cleanData.split('\n');
      while (lines.length > 1 && lines[lines.length - 1] === '') {
        lines.pop();
      }
      if (lines.length === 0) return;

      setLogs((prev) => {
        const appended = lines.map((content) => ({
          seq: ++retryGlobalSeq,
          content,
          timestamp: Date.now(),
        }));
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
      eventSourceRef.current = null;
    });

    es.onerror = () => {
      setConnected(false);
      es.close();
      eventSourceRef.current = null;

      // 重连时清空已有日志（服务端不支持断点续传）
      setLogs([]);

      // 指数退避重连
      const attempt = reconnectAttemptRef.current++;
      const delay = Math.min(RECONNECT_BASE_DELAY * 2 ** attempt, RECONNECT_MAX_DELAY);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => connect(), delay);
    };
  }, []);

  useEffect(() => {
    if (!runId || !retryId) return;
    connect();

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setConnected(false);
    };
  }, [runId, retryId, connect]);

  const clearLogs = useCallback(() => setLogs([]), []);

  return { logs, connected, autoScroll, setAutoScroll, clearLogs };
}
