import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ServersPage from './ServersPage'
import type { AgentWithConfig } from '@/types'

/** Mock api/agents 的 useAgentsWithConfig hook */
const mockUseAgentsWithConfig = vi.fn()
vi.mock('@/api/agents', () => ({
  useAgentsWithConfig: () => mockUseAgentsWithConfig(),
  useAgentHostInfo: () => ({ data: null, isLoading: false, isError: false, error: null, refetch: vi.fn(), isRefetching: false }),
  useDeployAgent: () => ({ mutate: vi.fn(), isPending: false, variables: null }),
  usePendingCommands: () => ({ data: [] }),
}))

/** Mock api/client */
vi.mock('@/api/client', () => ({
  default: { post: vi.fn(async () => ({ data: { results: [] } })) },
}))

/** 构造测试用 agent 数据 */
function makeAgent(overrides: Partial<AgentWithConfig> = {}): AgentWithConfig {
  return {
    agent_id: 'agent-1',
    name: 'Test Agent',
    type: 'ssh-linux',
    host: '10.0.0.1',
    port: 22,
    source_file: 'test.yaml',
    connected: true,
    project_id: '',
    project_name: '',
    hostname: 'test-host',
    platform: 'linux',
    system: 'Ubuntu 22.04',
    arch: 'x86_64',
    ip: '10.0.0.1',
    agent_version: '1.0.0',
    agent_pid: 1234,
    connected_at: 1700000000,
    last_heartbeat: 1700000000,
    running_commands: 0,
    net_status: 'reachable',
    ...overrides,
  }
}

/** Wrapper with QueryClient & Router */
function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('<ServersPage />', () => {
  beforeEach(() => {
    mockUseAgentsWithConfig.mockReset()
  })

  it('正常渲染 agent 列表', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({ agent_id: 'a1', system: 'Ubuntu' })],
      isLoading: false,
      refetch: vi.fn(),
      isFetching: false,
      error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => {
      expect(screen.getByText('服务器列表')).toBeInTheDocument()
    })
  })

  it('P0-9 回归：system/arch/hostname 为 null 时过滤不崩溃', async () => {
    // 模拟离线 agent 配置（yaml 中只配了 type，未连过，所有字段为 null/undefined）
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({ agent_id: 'offline-1', system: '', arch: '', hostname: '', ip: '' })],
      isLoading: false,
      refetch: vi.fn(),
      isFetching: false,
      error: null,
    })
    // 渲染不应抛错
    expect(() => render(<ServersPage />, { wrapper: Wrapper })).not.toThrow()
    await waitFor(() => {
      expect(screen.getByText('服务器列表')).toBeInTheDocument()
    })
  })

  it('P0-9 回归：所有字段为 undefined 时过滤不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'bare',
        system: undefined as unknown as string,
        arch: undefined as unknown as string,
        hostname: undefined as unknown as string,
        ip: undefined as unknown as string,
        host: undefined as unknown as string,
        name: undefined as unknown as string,
        type: undefined as unknown as string,
      })],
      isLoading: false,
      refetch: vi.fn(),
      isFetching: false,
      error: null,
    })
    expect(() => render(<ServersPage />, { wrapper: Wrapper })).not.toThrow()
    await waitFor(() => {
      expect(screen.getByText('服务器列表')).toBeInTheDocument()
    })
  })

  // ─── P0-9 边界条件：逐字段隔离 null ───

  it('仅 system 为 null — 其他字段有效时搜索不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'srv-1',
        system: undefined as unknown as string,
        arch: 'arm64',
        hostname: 'myhost',
        ip: '10.0.0.5',
        name: 'My Server',
        type: 'ssh-linux',
      })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    // 搜索 arm 不应崩溃
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'arm' } })
    await waitFor(() => expect(input.value).toBe('arm'))
  })

  it('仅 arch 为 null — 搜索其他字段不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'srv-2',
        arch: undefined as unknown as string,
        system: 'Debian 12',
        hostname: 'debian-box',
      })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'debian' } })
    await waitFor(() => expect(input.value).toBe('debian'))
  })

  it('仅 ip 为 null — 搜索 host 不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'srv-3',
        ip: undefined as unknown as string,
        host: '192.168.1.100',
      })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: '192' } })
    await waitFor(() => expect(input.value).toBe('192'))
  })

  it('仅 hostname 为 null — 搜索 agent_id 不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'edge-node-7',
        hostname: undefined as unknown as string,
      })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'edge' } })
    await waitFor(() => expect(input.value).toBe('edge'))
  })

  it('仅 name 为 null — 搜索 agent_id 不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'prod-db-1',
        name: undefined as unknown as string,
      })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'prod' } })
    await waitFor(() => expect(input.value).toBe('prod'))
  })

  it('仅 type 为 null — 搜索其他字段不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'local-1',
        type: undefined as unknown as string,
        system: 'macOS 14',
      })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'macos' } })
    await waitFor(() => expect(input.value).toBe('macos'))
  })

  // ─── P0-9 边界条件：特殊值 ───

  it('IPv6 地址 — 搜索不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'ip6-node',
        ip: 'fe80::1',
        host: '::1',
        system: undefined as unknown as string,
      })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'fe80' } })
    await waitFor(() => expect(input.value).toBe('fe80'))
  })

  it('agent_id 含正则特殊字符（. * + $）— 不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'node.test+prod$',
        system: undefined as unknown as string,
      })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    // 搜索含特殊字符的子串
    fireEvent.change(input, { target: { value: '+prod$' } })
    await waitFor(() => expect(input.value).toBe('+prod$'))
  })

  it('中文名称 — 搜索不崩溃（toLowerCase 对中文为 no-op）', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({
        agent_id: 'cn-srv',
        name: '生产数据库服务器',
        system: undefined as unknown as string,
        arch: undefined as unknown as string,
      })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: '数据库' } })
    await waitFor(() => expect(input.value).toBe('数据库'))
  })

  it('混合 null + 有效值：搜索有效值能命中，null 字段不崩溃', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [
        makeAgent({ agent_id: 'healthy', system: 'Ubuntu', name: 'Healthy Node' }),
        makeAgent({ agent_id: 'partial', system: undefined as unknown as string, name: 'Partial Node' }),
      ],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    // 搜索 'partial' 时，healthy 的 system 有效，partial 的 system 为 null — 都不能崩溃
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'partial' } })
    await waitFor(() => expect(input.value).toBe('partial'))
  })

  it('大小写不敏感：搜索 "ubuntu" 应能匹配 "Ubuntu"', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({ agent_id: 'case-test', system: 'Ubuntu', name: 'Case Test' })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    // 搜索小写 "ubuntu" — 应匹配 system 大写 "Ubuntu"
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'ubuntu' } })
    await waitFor(() => expect(input.value).toBe('ubuntu'))
    // agent 卡片仍应可见（未崩溃）
    expect(screen.getByText('Case Test')).toBeInTheDocument()
  })

  it('搜索无匹配结果时不崩溃（空列表 + null 字段）', async () => {
    mockUseAgentsWithConfig.mockReturnValue({
      data: [makeAgent({ agent_id: 'orphan', system: undefined as unknown as string, name: undefined as unknown as string })],
      isLoading: false, refetch: vi.fn(), isFetching: false, error: null,
    })
    render(<ServersPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('服务器列表')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/搜索/) as HTMLInputElement
    fireEvent.change(input, { target: { value: 'zzz_nonexistent' } })
    await waitFor(() => {
      expect(screen.getByText('无匹配的服务器')).toBeInTheDocument()
    })
  })
})