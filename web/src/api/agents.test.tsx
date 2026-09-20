import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useDeployAgent } from './agents';

const mockPost = vi.fn();

vi.mock('./client', () => ({
  default: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockPost(...args),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

// 静态 message 在无 App 上下文时会产生告警，测试只关心请求参数
vi.mock('antd', () => ({
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper };
}

describe('agents API hooks', () => {
  beforeEach(() => {
    mockPost.mockReset();
  });

  it('部署请求超时必须大于后端 60s 握手等待，否则 UI 先超时看不到诊断信息', async () => {
    mockPost.mockResolvedValue({ data: { success: true, agent_id: 'a1' } });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDeployAgent(), { wrapper });

    await result.current.mutateAsync('a1');

    expect(mockPost).toHaveBeenCalledWith(
      '/api/agents/deploy',
      { agent_id: 'a1', timeout: 30 },
      { timeout: 90000 },
    );
  });
});
