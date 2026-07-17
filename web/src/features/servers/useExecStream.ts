import { useState, useRef, useCallback } from 'react';
import { getToken } from '@/api/client';

export type ExecStatus = 'idle' | 'running' | 'done' | 'error';

export interface ExecLine {
  seq: number;
  type: 'command' | 'output' | 'error' | 'info';
  content: string;
  timestamp: number;
}

let globalSeq = 0;

interface SSEEvent {
  event: string;
  data: string;
}

/** 将 SSE 原始文本块解析为事件列表 */
function parseSSEChunk(chunk: string): SSEEvent[] {
  const events: SSEEvent[] = [];
  const blocks = chunk.split('\n\n');
  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = 'message';
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += line.slice(5).trimStart();
    }
    events.push({ event, data });
  }
  return events;
}

export function useExecStream() {
  const [lines, setLines] = useState<ExecLine[]>([]);
  const [status, setStatus] = useState<ExecStatus>('idle');
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async (agentId: string, command: string, timeout = 60) => {
    if (abortRef.current) abortRef.current.abort();

    const controller = new AbortController();
    abortRef.current = controller;

    setStatus('running');
    const cmdSeq = ++globalSeq;
    setLines((prev) => [
      ...prev,
      { seq: cmdSeq, type: 'command', content: command, timestamp: Date.now() },
    ]);

    const baseURL = (import.meta.env.VITE_API_BASE_URL as string) ?? '';
    const apiKey = (import.meta.env.VITE_API_KEY as string) ?? '';
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;
    // REPL 走 /api/agents 的 POST 接口，受 JWT 中间件保护，必须携带登录 token，
    // 否则会被中间件判定为「未登录或 token 无效」返回 401（即使已登录）。
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const append = (type: ExecLine['type'], content: string) => {
      setLines((prev) => [
        ...prev,
        { seq: ++globalSeq, type, content, timestamp: Date.now() },
      ]);
    };

    try {
      const resp = await fetch(`${baseURL}/api/agents/${agentId}/exec/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ command, timeout }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try {
          const body = await resp.text();
          const j = JSON.parse(body);
          if (j.detail) msg = j.detail;
        } catch { /* ignore */ }
        append('error', msg);
        setStatus('error');
        return;
      }

      const reader = resp.body?.getReader();
      if (!reader) {
        append('error', '无法读取响应流');
        setStatus('error');
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = parseSSEChunk(buffer);
        buffer = '';
        for (const evt of events) {
          if (evt.event === 'output') {
            append('output', evt.data);
          } else if (evt.event === 'result') {
            try {
              const r = JSON.parse(evt.data);
              if (r.exit_code !== 0 && r.exit_code !== undefined) {
                append('info', `[exit_code: ${r.exit_code}]`);
              }
              if (r.duration_ms) {
                append('info', `[耗时: ${r.duration_ms}ms]`);
              }
            } catch { /* ignore */ }
          } else if (evt.event === 'error') {
            try {
              const r = JSON.parse(evt.data);
              append('error', r.error || '执行出错');
            } catch {
              append('error', evt.data);
            }
            setStatus('error');
          } else if (evt.event === 'done') {
            setStatus('done');
          }
        }
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        append('info', '[已取消]');
      } else {
        append('error', String(e));
      }
      setStatus('error');
    }
  }, []);

  const cancel = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  const clear = useCallback(() => {
    setLines([]);
    setStatus('idle');
  }, []);

  const reset = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = null;
    setLines([]);
    setStatus('idle');
  }, []);

  return { lines, status, run, cancel, clear, reset };
}