/**
 * PipelineProgressPopover UX 补测（2026-09，QA 审计）。
 *
 * 覆盖维度：错误态 / 键盘可达性。
 * 背景：现有用例覆盖数据加载与时间格式；但 fetch 失败被静默吞掉，
 * 浮层 trigger 仅 hover（键盘用户无法打开）——两处体验缺口零覆盖。
 *
 * `it.fails` = 已确认缺陷（修复后改回 it）。
 * v2 (2026-09, issue #219/#221): 键盘 focus 打开与失败提示已实现，用例已转为常规断言。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import PipelineProgressPopover from '../PipelineProgressPopover'
import type { TaskRunResponse } from '@/types'

function makeTask(overrides: Partial<TaskRunResponse> = {}): TaskRunResponse {
  return {
    id: 'task-1',
    run_id: 'run-1',
    task_name: 'step1-init',
    subpipeline_name: 'deploy',
    task_type: 'command',
    status: 'success',
    exit_code: 0,
    error: null,
    log_path: '/tmp/log.txt',
    started_at: '2026-01-01T00:00:00Z',
    finished_at: '2026-01-01T00:01:00Z',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  mockFetch.mockReset()
})

describe('<PipelineProgressPopover /> UX-错误态', () => {
  it('UX-任务详情拉取失败时浮层展示失败提示，而不是静默停留旧数据', async () => {
    mockFetch.mockRejectedValue(new Error('Network Error'))
    render(
      <Wrapper>
        <PipelineProgressPopover runId="run-1">
          <span data-testid="trigger">hover me</span>
        </PipelineProgressPopover>
      </Wrapper>,
    )

    fireEvent.mouseEnter(screen.getByTestId('trigger'))
    await waitFor(() => expect(mockFetch).toHaveBeenCalled())

    expect(await screen.findByText(/加载失败|获取失败|网络错误/)).toBeInTheDocument()
  })
})

describe('<PipelineProgressPopover /> UX-键盘可达', () => {
  it('UX-键盘聚焦触发元素时可打开任务进度浮层（而非仅 hover）', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ tasks: [makeTask()] }) })
    render(
      <Wrapper>
        <PipelineProgressPopover runId="run-1">
          <button type="button" data-testid="trigger">查看任务</button>
        </PipelineProgressPopover>
      </Wrapper>,
    )

    fireEvent.focus(screen.getByTestId('trigger'))
    expect(await screen.findByText('step1-init')).toBeInTheDocument()
  })
})
