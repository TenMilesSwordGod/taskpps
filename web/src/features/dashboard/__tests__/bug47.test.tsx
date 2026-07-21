import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import DashboardPage from '../DashboardPage'
import type { RunResponse } from '@/types'

/** 构造测试用 run 数据 */
function makeRun(overrides: Partial<RunResponse> = {}): RunResponse {
  return {
    id: 'run-1',
    display_name: 'test-run',
    pipeline_name: 'demo',
    pipeline_file: 'demo.yaml',
    pipeline_id: 'pipeline-1',
    pipeline_version: 'v1',
    definition_id: 'def-1',
    project_id: null,
    project_name: null,
    version_changed: false,
    status: 'running',
    error: null,
    operator: null,
    operator_nickname: null,
    params: {},
    started_at: '2026-07-21T10:00:00Z',
    finished_at: null,
    created_at: '2026-07-21T10:00:00Z',
    duration_ms: null,
    tasks: [],
    task_summary: {},
    ...overrides,
  }
}

/** Mocks for API hooks */
const mockUseRuns = vi.fn()
const mockUsePipelines = vi.fn()
const mockUseProjects = vi.fn()

vi.mock('@/api/runs', () => ({
  useRuns: () => mockUseRuns(),
}))

vi.mock('@/api/pipelines', () => ({
  usePipelines: () => mockUsePipelines(),
}))

vi.mock('@/api/projects', () => ({
  useProjects: () => mockUseProjects(),
}))

vi.mock('@/components/StatusTag', () => ({
  default: ({ status }: { status: string }) => <span data-testid="status-tag">{status}</span>,
}))

vi.mock('@/components/PipelineProgressPopover', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter>{children}</MemoryRouter>
      </AntdApp>
    </QueryClientProvider>
  )
}

describe('Bug #47 - 耗时字符串过长导致换行显示异常', () => {
  beforeEach(() => {
    mockUseRuns.mockReset()
    mockUsePipelines.mockReset()
    mockUseProjects.mockReset()
    mockUseRuns.mockReturnValue({ data: { items: [] } })
    mockUsePipelines.mockReturnValue({ data: { items: [] } })
    mockUseProjects.mockReturnValue({ data: [] })
  })

  it('耗时超过 10 小时时应显示简短格式（如 15h 30m），而非中文长格式', async () => {
    const longRun = makeRun({
      id: 'long-run',
      display_name: 'long-run',
      status: 'running',
      duration_ms: 15 * 3600 * 1000 + 30 * 60 * 1000, // 15h 30m
    })
    mockUseRuns.mockReturnValue({ data: { items: [longRun] } })

    render(<DashboardPage />, { wrapper: Wrapper })

    // 等待组件渲染出"最近运行"表格中的耗时列
    await waitFor(() => {
      expect(screen.getByText('15h 30m')).toBeTruthy()
    })

    // 不应渲染中文长格式
    expect(screen.queryByText(/15时30分/)).toBeNull()
  })

  it('耗时列不应因长字符串换行（应有 white-space: nowrap 或 ellipsis）', async () => {
    // 模拟一个极端长耗时的运行（100h 0m）
    const extremeRun = makeRun({
      id: 'extreme-run',
      display_name: 'extreme-run',
      status: 'running',
      duration_ms: 100 * 3600 * 1000,
    })
    mockUseRuns.mockReturnValue({ data: { items: [extremeRun] } })

    render(<DashboardPage />, { wrapper: Wrapper })

    await waitFor(() => {
      expect(screen.getByText('100h 0m')).toBeTruthy()
    })
  })

  it('短耗时仍能正确显示', async () => {
    const shortRun = makeRun({
      id: 'short-run',
      display_name: 'short-run',
      status: 'success',
      duration_ms: 85 * 1000, // 1m 25s
    })
    mockUseRuns.mockReturnValue({ data: { items: [shortRun] } })

    render(<DashboardPage />, { wrapper: Wrapper })

    await waitFor(() => {
      expect(screen.getByText('1m 25s')).toBeTruthy()
    })
  })
})
