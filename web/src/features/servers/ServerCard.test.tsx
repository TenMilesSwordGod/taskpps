import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ServerCard from './ServerCard'
import type { AgentWithConfig, PendingCommandItem } from '@/types'

/** Mock api/agents 的 hooks */
const mockUsePendingCommands = vi.fn()
const mockUseDeployAgent = vi.fn()

vi.mock('@/api/agents', () => ({
  useDeployAgent: () => mockUseDeployAgent(),
  usePendingCommands: (agentId: string | undefined, enabled: boolean) => mockUsePendingCommands(agentId, enabled),
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
    max_parallel: 4,
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

describe('<ServerCard />', () => {
  beforeEach(() => {
    mockUsePendingCommands.mockReturnValue({ data: [] })
    mockUseDeployAgent.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      variables: null,
    })
  })

  it('显示运行中数量和最大并发', () => {
    render(<ServerCard agent={makeAgent({ running_commands: 2, max_parallel: 4 })} />, { wrapper: Wrapper })
    expect(screen.getByText('运行中 2 / 并发 4')).toBeInTheDocument()
  })

  it('max_parallel 缺失时默认显示为 1', () => {
    render(
      <ServerCard
        agent={makeAgent({ running_commands: 0, max_parallel: undefined as unknown as number })}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText('运行中 0 / 并发 1')).toBeInTheDocument()
  })

  it('无运行命令时状态不可点击且弹出空队列提示', async () => {
    render(<ServerCard agent={makeAgent({ running_commands: 0 })} />, { wrapper: Wrapper })
    const status = screen.getByText('运行中 0 / 并发 4')
    expect(status).toHaveAttribute('tabIndex', '-1')
    fireEvent.click(status)
    await waitFor(() => {
      expect(screen.queryByText('暂无运行中命令')).not.toBeInTheDocument()
    })
  })

  it('点击运行中状态展示按顺序编号的任务队列', async () => {
    const pending: PendingCommandItem[] = [
      {
        command_id: 'cmd-1',
        command: 'echo first',
        cwd: '/tmp',
        timeout: 60,
        run_id: 'run-abc',
        task_name: 'task-first',
        started_at: 1700000001,
        duration_s: 10,
      },
      {
        command_id: 'cmd-2',
        command: 'echo second',
        cwd: '/tmp',
        timeout: 60,
        run_id: 'run-def',
        task_name: 'task-second',
        started_at: 1700000002,
        duration_s: 5,
      },
    ]
    mockUsePendingCommands.mockReturnValue({ data: pending })

    render(<ServerCard agent={makeAgent({ running_commands: 2 })} />, { wrapper: Wrapper })
    fireEvent.click(screen.getByText('运行中 2 / 并发 4'))

    await waitFor(() => {
      expect(screen.getByText('执行队列（2 / 最大并发 4）')).toBeInTheDocument()
    })

    // 队列按传入顺序展示编号
    const first = screen.getByText('task-first')
    const second = screen.getByText('task-second')
    expect(first).toBeInTheDocument()
    expect(second).toBeInTheDocument()
    expect(first.previousElementSibling?.textContent).toBe('1')
    expect(second.previousElementSibling?.textContent).toBe('2')
  })

  it('队列中显示可点击的 run_id 链接', async () => {
    const pending: PendingCommandItem[] = [
      {
        command_id: 'cmd-1',
        command: 'echo first',
        cwd: '/tmp',
        timeout: 60,
        run_id: 'run-abc',
        task_name: 'task-first',
        started_at: 1700000001,
        duration_s: 10,
      },
    ]
    mockUsePendingCommands.mockReturnValue({ data: pending })

    render(<ServerCard agent={makeAgent({ running_commands: 1 })} />, { wrapper: Wrapper })
    fireEvent.click(screen.getByText('运行中 1 / 并发 4'))

    await waitFor(() => {
      expect(screen.getByText('task-first')).toBeInTheDocument()
    })

    // run_id 前 8 位可点击
    const runLink = screen.getByText('run-abc'.slice(0, 8))
    expect(runLink).toBeInTheDocument()
    expect(() => fireEvent.click(runLink)).not.toThrow()
  })
})
