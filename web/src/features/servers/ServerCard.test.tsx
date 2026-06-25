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
    queued_commands: 0,
    max_parallel: 4,
    net_status: 'reachable',
    last_execution_time: 0,
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

  it('显示运行中、等待中数量和最大并发', () => {
    render(
      <ServerCard agent={makeAgent({ running_commands: 2, queued_commands: 3, max_parallel: 4 })} />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText('运行中 2 / 等待中 3 / 并发 4')).toBeInTheDocument()
  })

  it('max_parallel 缺失时默认显示为 1', () => {
    render(
      <ServerCard
        agent={makeAgent({ running_commands: 0, queued_commands: 0, max_parallel: undefined as unknown as number })}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText('运行中 0 / 等待中 0 / 并发 1')).toBeInTheDocument()
  })

  it('无运行/等待命令时状态不可点击且不会弹出空队列', async () => {
    render(<ServerCard agent={makeAgent({ running_commands: 0, queued_commands: 0 })} />, { wrapper: Wrapper })
    const status = screen.getByText('运行中 0 / 等待中 0 / 并发 4')
    expect(status).toHaveAttribute('tabIndex', '-1')
    fireEvent.click(status)
    await waitFor(() => {
      expect(screen.queryByText('暂无运行中或等待中命令')).not.toBeInTheDocument()
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
        status: 'running',
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
        status: 'running',
      },
    ]
    mockUsePendingCommands.mockReturnValue({ data: pending })

    render(<ServerCard agent={makeAgent({ running_commands: 2 })} />, { wrapper: Wrapper })
    fireEvent.click(screen.getByText('运行中 2 / 等待中 0 / 并发 4'))

    await waitFor(() => {
      expect(screen.getByText('执行队列（运行中 2 + 等待中 0 / 最大并发 4）')).toBeInTheDocument()
    })

    // 队列按传入顺序展示编号
    const first = screen.getByText('task-first')
    const second = screen.getByText('task-second')
    expect(first).toBeInTheDocument()
    expect(second).toBeInTheDocument()
    expect(first.previousElementSibling?.textContent).toBe('1')
    expect(second.previousElementSibling?.textContent).toBe('2')
  })

  it('队列中同时显示运行中和等待中任务分组', async () => {
    const pending: PendingCommandItem[] = [
      {
        command_id: 'cmd-running',
        command: 'echo running',
        cwd: '/tmp',
        timeout: 60,
        run_id: 'run-abc',
        task_name: 'task-running',
        started_at: 1700000001,
        duration_s: 10,
        status: 'running',
      },
      {
        command_id: 'cmd-queued',
        command: 'echo queued',
        cwd: '/tmp',
        timeout: 60,
        run_id: 'run-def',
        task_name: 'task-queued',
        started_at: 0,
        duration_s: 0,
        status: 'queued',
      },
    ]
    mockUsePendingCommands.mockReturnValue({ data: pending })

    render(
      <ServerCard agent={makeAgent({ running_commands: 1, queued_commands: 1 })} />,
      { wrapper: Wrapper },
    )
    fireEvent.click(screen.getByText('运行中 1 / 等待中 1 / 并发 4'))

    await waitFor(() => {
      expect(screen.getByText('执行队列（运行中 1 + 等待中 1 / 最大并发 4）')).toBeInTheDocument()
      expect(screen.getByText('运行中 (1)')).toBeInTheDocument()
      expect(screen.getByText('等待中 (1)')).toBeInTheDocument()
      expect(screen.getByText('task-running')).toBeInTheDocument()
      expect(screen.getByText('task-queued')).toBeInTheDocument()
    })
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
        status: 'running',
      },
    ]
    mockUsePendingCommands.mockReturnValue({ data: pending })

    render(<ServerCard agent={makeAgent({ running_commands: 1 })} />, { wrapper: Wrapper })
    fireEvent.click(screen.getByText('运行中 1 / 等待中 0 / 并发 4'))

    await waitFor(() => {
      expect(screen.getByText('task-first')).toBeInTheDocument()
    })

    // run_id 前 8 位可点击
    const runLink = screen.getByText('run-abc'.slice(0, 8))
    expect(runLink).toBeInTheDocument()
    expect(() => fireEvent.click(runLink)).not.toThrow()
  })

  describe('LastExecTime', () => {
    it('无执行记录时显示"暂无执行记录"', () => {
      render(
        <ServerCard agent={makeAgent({ last_execution_time: 0 })} />,
        { wrapper: Wrapper },
      )
      expect(screen.getByText('暂无执行记录')).toBeInTheDocument()
    })

    it('有执行记录时显示绝对时间格式', () => {
      // 使用固定时间戳验证格式：2026-05-23 12:23:11 UTC = 1766186591
      const ts = 1766186591
      render(
        <ServerCard agent={makeAgent({ last_execution_time: ts })} />,
        { wrapper: Wrapper },
      )
      // 检查显示格式 YYYY-MM-DD HH:mm:ss
      const timeText = screen.getByText(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
      expect(timeText).toBeInTheDocument()
    })

    it('点击时间切换为相对时间格式', async () => {
      // 使用一个已知的时间戳，方便验证相对时间
      const now = Math.floor(Date.now() / 1000)
      const ts = now - 125 // 2分钟前
      render(
        <ServerCard agent={makeAgent({ last_execution_time: ts })} />,
        { wrapper: Wrapper },
      )
      const timeEl = screen.getByText(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
      fireEvent.click(timeEl)
      await waitFor(() => {
        expect(screen.getByText('2分钟前')).toBeInTheDocument()
      })
    })
  })
})
