import { useState, useRef, useCallback } from 'react';
import { execCommandStream, type ExecStatus, type ExecLine } from './execStream';

export type { ExecStatus, ExecLine };

let globalSeq = 0;

interface SSEEvent {
  event: string;
  data: string;
}

/** 将 SSE 原始文本块解析为事件列表，返回未完成尾部供下次拼接 */
export function parseSSEChunk(chunk: string): { events: SSEEvent[]; rest: string } {
  // 规范化换行符：\r\n → \n，残留 \r → \n（兼容 sse-starlette 的 CRLF 输出）
  const normalized = chunk.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const events: SSEEvent[] = [];
  const blocks = normalized.split('\n\n');
  // 最后一个 block 可能不完整（TCP 包边界落在 SSE event 中间），留到下次拼完再解析
  const rest = blocks.pop() ?? '';
  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = 'message';
    const dataLines: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) {
        // v2: data: 后可选一个空格（SSE 规范），该空格不属于内容
        const raw = line.slice(5);
        dataLines.push(raw.startsWith(' ') ? raw.slice(1) : raw);
      }
    }
    events.push({ event, data: dataLines.join('\n') }); // v2: 用 \n 重新拼接多行 data，取代原来的裸拼接
  }
  return { events, rest };
}

export function useExecStream() {
  const [lines, setLines] = useState<ExecLine[]>([]);
  const [status, setStatus] = useState<ExecStatus>('idle');
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async (
    agentId: string, command: string, timeout = 60, cwd = '',
  ) => {
    if (abortRef.current) abortRef.current.abort();

    const controller = new AbortController();
    abortRef.current = controller;

    setStatus('running');

    const append = (line: ExecLine) => {
      setLines((prev) => [...prev, { ...line, seq: ++globalSeq }]);
    };

    await execCommandStream(agentId, command, timeout, cwd, controller.signal, {
      onAppend: append,
      onStatus: setStatus,
    });
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
