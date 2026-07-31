import { getToken } from '@/api/client';
import { parseSSEChunk } from './useExecStream';

export type ExecStatus = 'idle' | 'running' | 'done' | 'error';

export interface ExecLine {
  seq: number;
  type: 'command' | 'output' | 'error' | 'info';
  content: string;
  timestamp: number;
}

export interface ExecStreamCallbacks {
  onAppend: (line: ExecLine) => void;
  onStatus: (status: ExecStatus) => void;
}

let globalSeq = 0;

/** 执行命令并流式读取 SSE 输出，通过回调通知调用方 */
export async function execCommandStream(
  agentId: string,
  command: string,
  timeout: number,
  cwd: string,
  signal: AbortSignal,
  callbacks: ExecStreamCallbacks,
): Promise<void> {
  const { onAppend, onStatus } = callbacks;

  const cmdSeq = ++globalSeq;
  onAppend({
    seq: cmdSeq,
    type: 'command',
    content: command,
    timestamp: Date.now(),
  });

  const baseURL = (import.meta.env.VITE_API_BASE_URL as string) ?? '';
  const apiKey = (import.meta.env.VITE_API_KEY as string) ?? '';
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) headers['X-API-Key'] = apiKey;
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  try {
    const resp = await fetch(`${baseURL}/api/agents/${agentId}/exec/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ command, timeout, cwd }),
      signal,
    });

    if (!resp.ok) {
      let msg = `HTTP ${resp.status}`;
      try {
        const body = await resp.text();
        const j = JSON.parse(body);
        if (j.detail) msg = j.detail;
      } catch { /* ignore */ }
      onAppend({ seq: ++globalSeq, type: 'error', content: msg, timestamp: Date.now() });
      onStatus('error');
      return;
    }

    const reader = resp.body?.getReader();
    if (!reader) {
      onAppend({ seq: ++globalSeq, type: 'error', content: '无法读取响应流', timestamp: Date.now() });
      onStatus('error');
      return;
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSSEChunk(buffer);
      buffer = rest;
      for (const evt of events) {
        if (evt.event === 'output') {
          onAppend({ seq: ++globalSeq, type: 'output', content: evt.data, timestamp: Date.now() });
        } else if (evt.event === 'result') {
          try {
            const r = JSON.parse(evt.data);
            const parts: string[] = [];
            if (r.exit_code !== undefined) {
              parts.push(`exit_code: ${r.exit_code}`);
            }
            if (r.duration_ms !== undefined) {
              parts.push(`${r.duration_ms}ms`);
            }
            if (parts.length > 0) {
              onAppend({ seq: ++globalSeq, type: 'info', content: parts.join(' · '), timestamp: Date.now() });
            }
          } catch { /* ignore */ }
        } else if (evt.event === 'error') {
          try {
            const r = JSON.parse(evt.data);
            onAppend({ seq: ++globalSeq, type: 'error', content: r.error || '执行出错', timestamp: Date.now() });
          } catch {
            onAppend({ seq: ++globalSeq, type: 'error', content: evt.data, timestamp: Date.now() });
          }
          onStatus('error');
        } else if (evt.event === 'done') {
          onStatus('done');
        }
      }
    }
  } catch (e) {
    if ((e as Error).name === 'AbortError') {
      onAppend({ seq: ++globalSeq, type: 'info', content: '[已取消]', timestamp: Date.now() });
    } else {
      onAppend({ seq: ++globalSeq, type: 'error', content: String(e), timestamp: Date.now() });
    }
    onStatus('error');
  }
}
