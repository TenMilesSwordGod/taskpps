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

describe('<PipelineProgressPopover /> Issue #94 - 悬浮窗优化', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('完成时间应携带月日（MM-DD HH:mm:ss 格式）', async () => {
    const tasks = [
      makeTask({
        task_name: 'step1-init',
        status: 'success',
        finished_at: '2026-06-22T14:01:42Z',
      }),
    ]

    mockFetch.mockImplementation(async (url: string) => {
      if (url === '/api/runs/run-1') {
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

    fireEvent.mouseEnter(screen.getByTestId('trigger'))

    // 等待数据加载后，验证时间格式包含月日（MM-DD 前缀）
    await waitFor(() => {
      // dayjs 在不同时区可能输出不同时间，但格式一定是 MM-DD HH:mm:ss
      const timeEl = document.querySelector('[data-testid="task-time"]')
      expect(timeEl).toBeTruthy()
      const text = timeEl?.textContent ?? ''
      // 格式应为 MM-DD HH:mm:ss，即以两位月-两位日开头
      expect(text).toMatch(/^\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
    })
  })

  it('完成时间和状态图标应显示在任务名下方（非同行右侧）', async () => {
    const tasks = [
      makeTask({
        task_name: 'step1-init',
        status: 'success',
        finished_at: '2026-06-22T14:01:42Z',
      }),
      makeTask({
        id: 'task-2',
        task_name: 'step2-build',
        status: 'failed',
        finished_at: '2026-06-22T14:05:00Z',
      }),
    ]

    mockFetch.mockImplementation(async (url: string) => {
      if (url === '/api/runs/run-1') {
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

    fireEvent.mouseEnter(screen.getByTestId('trigger'))

    await waitFor(() => {
      expect(screen.getByText('step1-init')).toBeInTheDocument()
    })

    // 任务行应该是纵向布局（flex-direction: column），时间在任务名下方
    const taskRows = document.querySelectorAll('[data-testid="task-row"]')
    expect(taskRows.length).toBeGreaterThan(0)
    for (const row of Array.from(taskRows)) {
      const style = (row as HTMLElement).style
      expect(style.flexDirection).toBe('column')
    }
  })

  it('panel 内容区域高度应足够大以减少滚动条', async () => {
    const tasks = [
      makeTask({ task_name: 'step1-init', status: 'success', finished_at: '2026-06-22T14:01:42Z' }),
    ]

    mockFetch.mockImplementation(async (url: string) => {
      if (url === '/api/runs/run-1') {
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

    fireEvent.mouseEnter(screen.getByTestId('trigger'))

    await waitFor(() => {
      expect(screen.getByText('step1-init')).toBeInTheDocument()
    })

    // 验证内容区域 maxHeight >= 480
    const scrollContainer = document.querySelector('[data-testid="task-list-scroll"]')
    expect(scrollContainer).toBeTruthy()
    const style = (scrollContainer as HTMLElement).style
    expect(parseInt(style.maxHeight)).toBeGreaterThanOrEqual(480)
  })
})

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
    // 运行中任务显示 Loader2 转圈图标（不再显示 RUN 文字）
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()

    // 关闭 popover：直接触发 mouseLeave
    fireEvent.mouseLeave(trigger)
    await act(async () => { await new Promise((r) => setTimeout(r, 350)) })

    // 第二次 hover
    fireEvent.mouseEnter(trigger)
    await waitFor(() => expect(fetchCallCount).toBe(2), { timeout: 3000 })

    // 验证更新后的状态
    await waitFor(() => expect(screen.getByText('step2-prepare')).toBeInTheDocument())
    // 运行中任务显示 Loader2 转圈图标
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
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
