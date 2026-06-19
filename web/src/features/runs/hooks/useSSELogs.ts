import { useState, useEffect, useRef, useCallback } from 'react';

import type { TaskStatus } from '@/types';

export interface LogEntry {
  /** 全局自增序列号，保证同毫秒内多条日志 key 唯一 */
  seq: number;
  taskName: string;
  content: string;
  timestamp: number;
}

/** 任务状态变更事件 */
export interface TaskStatusUpdate {
  task_name: string;
  status: TaskStatus;
}

/** 日志最大行数（DOM 性能保护） */
const MAX_LOG_LINES = 50000;

/** 全局日志序列号（模块级，避免 hook 重 mount 后 seq 回零导致冲突） */
let globalSeq = 0;

/** SSE 重连基础延迟（ms），实际延迟 = base * 2^attempt，上限 10s */
const RECONNECT_BASE_DELAY = 1000;
const RECONNECT_MAX_DELAY = 10000;

/** SSE 实时日志 hook */
export function useSSELogs(runId: string | undefined) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [taskStatusMap, setTaskStatusMap] = useState<Record<string, TaskStatus>>({});
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const runIdRef = useRef(runId);
  runIdRef.current = runId;

  const connect = useCallback(() => {
    const currentRunId = runIdRef.current;
    if (!currentRunId) return;

    // 清理旧连接
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const es = new EventSource(`/api/runs/${currentRunId}/logs?follow=true`);
    eventSourceRef.current = es;

    es.onopen = () => {
      setConnected(true);
      reconnectAttemptRef.current = 0;
    };

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

    es.addEventListener('status', (e) => {
      const data = e.data as string;
      if (!data) return;
      try {
        const update: TaskStatusUpdate = JSON.parse(data);
        setTaskStatusMap((prev) => ({ ...prev, [update.task_name]: update.status }));
      } catch {
        // ignore malformed status events
      }
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

      // 重连：清除可能过期的 taskStatusMap，避免陈旧状态覆盖服务端最新数据
      // （Issue #61: SSE 断连后 taskStatusMap 停留在旧状态，导致 UI 状态不更新）
      setTaskStatusMap({});

      // 指数退避重连
      const attempt = reconnectAttemptRef.current++;
      const delay = Math.min(RECONNECT_BASE_DELAY * 2 ** attempt, RECONNECT_MAX_DELAY);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => connect(), delay);
    };
  }, []);

  useEffect(() => {
    if (!runId) return;
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
  }, [runId, connect]);

  const clearLogs = useCallback(() => setLogs([]), []);

  return { logs, connected, autoScroll, setAutoScroll, clearLogs, taskStatusMap };
}
