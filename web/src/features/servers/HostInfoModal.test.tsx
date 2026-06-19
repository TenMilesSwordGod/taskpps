import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import HostInfoModal from './HostInfoModal'
import type { AgentWithConfig, AgentHostInfo, DiskInfo } from '@/types'

/** Mock useAgentHostInfo */
const mockUseAgentHostInfo = vi.fn()
vi.mock('@/api/agents', () => ({
  useAgentHostInfo: (...args: unknown[]) => mockUseAgentHostInfo(...args),
}))

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

function makeDisk(overrides: Partial<DiskInfo> = {}): DiskInfo {
  return {
    filesystem: '/dev/sda1',
    size: '63G',
    used: '49G',
    avail: '12G',
    percent: 78,
    mount: '/',
    ...overrides,
  }
}

function makeHostInfo(overrides: Partial<AgentHostInfo> = {}): AgentHostInfo {
  return {
    agent_id: 'agent-1',
    hostname: 'test-host',
    kernel: 'Linux test-host 5.15.0',
    os_release: 'PRETTY_NAME="Ubuntu 22.04"',
    uptime: 'up 3 days',
    cpu: { model: 'Intel Xeon', cores: 4, threads: 8 },
    memory: { total: '16Gi', used: '4Gi', free: '12Gi', percent: 25 },
    disks: [makeDisk()],
    source: 'ssh',
    ...overrides,
  }
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('<HostInfoModal />', () => {
  beforeEach(() => {
    mockUseAgentHostInfo.mockReset()
  })

  it('正常渲染磁盘列表', async () => {
    mockUseAgentHostInfo.mockReturnValue({
      data: makeHostInfo({ disks: [makeDisk({ mount: '/' }), makeDisk({ mount: '/var', filesystem: '/dev/sda2' })] }),
      isLoading: false, isError: false, refetch: vi.fn(), isRefetching: false,
    })
    render(<HostInfoModal open={true} agent={makeAgent()} onClose={vi.fn()} />, { wrapper: Wrapper })
    await waitFor(() => {
      expect(screen.getByText('/')).toBeInTheDocument()
      expect(screen.getByText('/var')).toBeInTheDocument()
    })
  })

  it('issue #64：磁盘超过阈值时折叠，点击展开', async () => {
    // 8 个磁盘 > 阈值 6，默认只显示 5 个
    const disks = Array.from({ length: 8 }, (_, i) =>
      makeDisk({ mount: `/vol${i}`, filesystem: `/dev/sd${i}` }),
    )
    mockUseAgentHostInfo.mockReturnValue({
      data: makeHostInfo({ disks }),
      isLoading: false, isError: false, refetch: vi.fn(), isRefetching: false,
    })
    render(<HostInfoModal open={true} agent={makeAgent()} onClose={vi.fn()} />, { wrapper: Wrapper })

    await waitFor(() => {
      // 前 5 个可见
      expect(screen.getByText('/vol0')).toBeInTheDocument()
      expect(screen.getByText('/vol4')).toBeInTheDocument()
      // 第 6 个不可见
      expect(screen.queryByText('/vol5')).not.toBeInTheDocument()
    })
    // 展开按钮存在
    expect(screen.getByText(/展开剩余 3 个挂载点/)).toBeInTheDocument()

    // 点击展开
    fireEvent.click(screen.getByText(/展开剩余 3 个挂载点/))
    await waitFor(() => {
      expect(screen.getByText('/vol5')).toBeInTheDocument()
      expect(screen.getByText('/vol7')).toBeInTheDocument()
      expect(screen.getByText('收起')).toBeInTheDocument()
    })
  })

  it('磁盘少于阈值时不显示折叠按钮', async () => {
    mockUseAgentHostInfo.mockReturnValue({
      data: makeHostInfo({ disks: [makeDisk({ mount: '/' }), makeDisk({ mount: '/var', filesystem: '/dev/sda2' })] }),
      isLoading: false, isError: false, refetch: vi.fn(), isRefetching: false,
    })
    render(<HostInfoModal open={true} agent={makeAgent()} onClose={vi.fn()} />, { wrapper: Wrapper })
    await waitFor(() => {
      expect(screen.getByText('/')).toBeInTheDocument()
    })
    expect(screen.queryByText(/展开剩余/)).not.toBeInTheDocument()
    expect(screen.queryByText('收起')).not.toBeInTheDocument()
  })
})
