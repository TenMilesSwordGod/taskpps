import { getToken } from '@/api/client';

export interface CompletionResult {
  prefix: string;
  candidates: string[];
}

/**
 * 请求 Web REPL 补全（POST /api/agents/{id}/complete）。
 *
 * 返回 null 表示"无可补全"（agent 离线/服务异常/agent 侧补全失败/超时）——
 * 这是需求明确的 UI 行为：补全失败静默保持原输入，不打断用户。
 * 注意：error 字段在此被消费而非吞掉，前端不会拿假数据兜底。
 */
export async function fetchCompletions(
  agentId: string,
  line: string,
  cursor: number,
  cwd: string,
  signal: AbortSignal,
): Promise<CompletionResult | null> {
  const baseURL = (import.meta.env.VITE_API_BASE_URL as string) ?? '';
  const apiKey = (import.meta.env.VITE_API_KEY as string) ?? '';
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) headers['X-API-Key'] = apiKey;
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  try {
    const resp = await fetch(`${baseURL}/api/agents/${agentId}/complete`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ line, cursor, cwd }),
      signal,
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    if (data?.error) return null;
    return { prefix: data.prefix ?? '', candidates: data.candidates ?? [] };
  } catch {
    // AbortError（输入变化取消旧请求）与网络异常统一按"无可补全"处理
    return null;
  }
}
