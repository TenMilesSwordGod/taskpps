import { afterEach, describe, expect, it, vi } from 'vitest';

// fetchCompletions 是纯 fetch 封装，mock 全局 fetch 验证请求/响应处理

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

afterEach(() => {
  mockFetch.mockReset();
});

describe('fetchCompletions', () => {
  it('请求 complete 端点并返回 prefix/candidates', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ request_id: 'r1', prefix: 'ls', candidates: ['ls', 'lsblk'], error: '' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const { fetchCompletions } = await import('./complete');
    const result = await fetchCompletions('agent-1', 'ls', 2, '/tmp', new AbortController().signal);

    expect(result).toEqual({ prefix: 'ls', candidates: ['ls', 'lsblk'] });
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toContain('/api/agents/agent-1/complete');
    expect(JSON.parse(init.body)).toEqual({ line: 'ls', cursor: 2, cwd: '/tmp' });
  });

  it('agent 侧 error 时返回 null（UI 静默）', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ prefix: '', candidates: [], error: 'completion timeout' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const { fetchCompletions } = await import('./complete');
    const result = await fetchCompletions('agent-1', 'ls', 2, '', new AbortController().signal);
    expect(result).toBeNull();
  });

  it('非 2xx（如 agent 离线 404）时返回 null', async () => {
    mockFetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'not connected' }), { status: 404 }));
    const { fetchCompletions } = await import('./complete');
    const result = await fetchCompletions('agent-1', 'ls', 2, '', new AbortController().signal);
    expect(result).toBeNull();
  });

  it('网络异常（Abort/TypeError）时返回 null', async () => {
    mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const { fetchCompletions } = await import('./complete');
    const result = await fetchCompletions('agent-1', 'ls', 2, '', new AbortController().signal);
    expect(result).toBeNull();
  });

  it('空候选时返回空数组而非 null（无候选也是合法结果）', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ prefix: 'zzz', candidates: [], error: '' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const { fetchCompletions } = await import('./complete');
    const result = await fetchCompletions('agent-1', 'zzz', 3, '', new AbortController().signal);
    expect(result).toEqual({ prefix: 'zzz', candidates: [] });
  });
});
