import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PipelineProgressPopover from './PipelineProgressPopover'
import type { TaskRunResponse } from '@/types'

/** 构造测试用 task 数据 */
function makeTask(overrides: Partial<TaskRunResponse> = {}): TaskRunResponse {
  return {
    id: 'task-1',
    run_id: 'run-1',
    task_name: 'step1-init',
    subpipeline_name: 'debug-sequential',
    task_type: 'command',
    status: 'running',
    exit_code: null,
    error: null,
    log_path: '/tmp/log.txt',
    started_at: '2026-01-01T00:00:00Z',
    finished_at: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

/** Mock fetch 全局方法 */
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

/** Wrapper: QueryClient */
function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      {children}
    </QueryClientProvider>
  )
}

describe('<PipelineProgressPopover /> Issue #82 - 悬浮窗动态加载', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('每次 hover 都应重新获取最新任务状态', async () => {
    const runningTasks = [
      makeTask({ task_name: 'step1-init', status: 'running' }),
      makeTask({ id: 'task-2', task_name: 'step2-prepare', status: 'pending' }),
    ]
    const updatedTasks = [
      makeTask({ task_name: 'step1-init', status: 'success' }),
      makeTask({ id: 'task-2', task_name: 'step2-prepare', status: 'running' }),
    ]

    let fetchCallCount = 0
    mockFetch.mockImplementation(async (url: string) => {
      if (url === '/api/runs/run-1') {
        fetchCallCount++
        const tasks = fetchCallCount === 1 ? runningTasks : updatedTasks
        return { ok: true, json: async () => ({ tasks }) }
      }
      return { ok: false, json: async () => ({}) }
    })

    render(
      <Wrapper>
        <PipelineProgressPopover runId="run-1">
          <span data-testid="trigger">hover me</span>
        </PipelineProgressPopover>
      </Wrapper>,
    )

    const trigger = screen.getByTestId('trigger')

    // 第一次 hover
    fireEvent.mouseEnter(trigger)
    await waitFor(() => expect(fetchCallCount).toBe(1))
    await waitFor(() => expect(screen.getByText('step1-init')).toBeInTheDocument())
    expect(screen.getByText('RUN')).toBeInTheDocument()

    // 关闭 popover：直接触发 mouseLeave
    fireEvent.mouseLeave(trigger)
    await act(async () => { await new Promise((r) => setTimeout(r, 350)) })

    // 第二次 hover
    fireEvent.mouseEnter(trigger)
    await waitFor(() => expect(fetchCallCount).toBe(2), { timeout: 3000 })

    // 验证更新后的状态
    await waitFor(() => expect(screen.getByText('step2-prepare')).toBeInTheDocument())
    const runLabels = screen.getAllByText('RUN')
    expect(runLabels.length).toBe(1)
  })

  it('有 tasks prop 时，hover 也应重新获取最新状态', async () => {
    const initialTasks = [
      makeTask({ task_name: 'step1-init', status: 'running' }),
    ]
    const updatedTasks = [
      makeTask({ task_name: 'step1-init', status: 'success' }),
    ]

    mockFetch.mockImplementation(async (url: string) => {
      if (url === '/api/runs/run-2') {
        return { ok: true, json: async () => ({ tasks: updatedTasks }) }
      }
      return { ok: false, json: async () => ({}) }
    })

    render(
      <Wrapper>
        <PipelineProgressPopover runId="run-2" tasks={initialTasks} taskSummary={{ running: 1 }}>
          <span data-testid="trigger">hover me</span>
        </PipelineProgressPopover>
      </Wrapper>,
    )

    const trigger = screen.getByTestId('trigger')
    fireEvent.mouseEnter(trigger)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/runs/run-2')
    })
    await waitFor(() => {
      expect(screen.queryByText('RUN')).not.toBeInTheDocument()
    })
  })

  it('无 runId 时不应发送请求', async () => {
    render(
      <Wrapper>
        <PipelineProgressPopover taskSummary={{ success: 3, running: 1 }}>
          <span data-testid="trigger">hover me</span>
        </PipelineProgressPopover>
      </Wrapper>,
    )

    const trigger = screen.getByTestId('trigger')
    fireEvent.mouseEnter(trigger)
    expect(mockFetch).not.toHaveBeenCalled()
  })
})
