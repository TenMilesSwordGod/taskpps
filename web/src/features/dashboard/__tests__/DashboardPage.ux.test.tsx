/**
 * DashboardPage UX 补测（2026-09，QA 审计）。
 *
 * 覆盖维度：加载态 / 错误态 / 刷新入口。
 * 背景：现有用例只覆盖耗时列格式（bug47）与趋势图宽度 bug；首屏统计卡在
 * 加载中固定显示 0（数据回来跳变）、接口失败无任何提示、无手动刷新入口，
 * 三处体验缺口零覆盖，故新增本文件。
 * v2 (2026-09, issue #217): 骨架/错误提示/刷新入口已实现，用例已转为常规断言。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import DashboardPage from '../DashboardPage'
import type { RunResponse } from '@/types'

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

const mockUseRuns = vi.fn()
const mockUsePipelines = vi.fn()
const mockUseProjects = vi.fn()

vi.mock('@/api/runs', () => ({ useRuns: () => mockUseRuns() }))
vi.mock('@/api/pipelines', () => ({ usePipelines: () => mockUsePipelines() }))
vi.mock('@/api/projects', () => ({ useProjects: () => mockUseProjects() }))
vi.mock('@/components/StatusTag', () => ({
  default: ({ status }: { status: string }) => <span data-testid="status-tag">{status}</span>,
}))
vi.mock('@/components/PipelineProgressPopover', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('@/features/dashboard/components/TrendLineChart', () => ({
  default: () => <div data-testid="trend-chart" />,
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

beforeEach(() => {
  mockUseRuns.mockReset()
  mockUsePipelines.mockReset()
  mockUseProjects.mockReset()
})

describe('<DashboardPage /> UX-加载态', () => {
  it('UX-首屏加载中统计卡展示占位而不是数字 0（避免 0 → 真实值跳变误导）', () => {
    mockUsePipelines.mockReturnValue({ data: undefined, isLoading: true })
    mockUseRuns.mockReturnValue({ data: undefined, isLoading: true })
    mockUseProjects.mockReturnValue({ data: undefined, isLoading: true })
    const { container } = render(<DashboardPage />, { wrapper: Wrapper })

    expect(container.querySelector('.ant-skeleton')).not.toBeNull()
    // 加载中不允许任何统计卡展示确定的 0
    const zeroShown = Array.from(container.querySelectorAll('.ant-statistic-content-value'))
      .some((el) => el.textContent?.trim() === '0')
    expect(zeroShown).toBe(false)
  })
})

describe('<DashboardPage /> UX-错误态', () => {
  it('UX-统计接口失败时展示失败提示与重试，而不是静默显示 0', async () => {
    mockUsePipelines.mockReturnValue({ data: undefined, isLoading: false, error: new Error('500'), refetch: vi.fn() })
    mockUseRuns.mockReturnValue({ data: undefined, isLoading: false, error: new Error('500'), refetch: vi.fn() })
    mockUseProjects.mockReturnValue({ data: undefined, isLoading: false, error: new Error('500'), refetch: vi.fn() })
    render(<DashboardPage />, { wrapper: Wrapper })

    expect(await screen.findByText(/加载失败|无法获取|请求失败/)).toBeInTheDocument()
    // 错误 Alert 的「重试」+ 顶部「刷新」都应存在（至少一个可恢复入口）
    expect(screen.getAllByRole('button', { name: /重\s*试|刷新/ }).length).toBeGreaterThan(0)
  })
})

describe('<DashboardPage /> UX-刷新入口', () => {
  it('UX-看板提供手动刷新入口', () => {
    mockUsePipelines.mockReturnValue({ data: { items: [] }, isLoading: false })
    mockUseRuns.mockReturnValue({ data: { items: [] }, isLoading: false })
    mockUseProjects.mockReturnValue({ data: [], isLoading: false })
    render(<DashboardPage />, { wrapper: Wrapper })

    expect(screen.getByRole('button', { name: /刷新/ })).toBeInTheDocument()
  })
})

describe('<DashboardPage /> UX-基线（已有正确行为回归）', () => {
  it('UX-数据加载完成后统计卡展示真实数值', () => {
    mockUsePipelines.mockReturnValue({ data: { items: [{}, {}] }, isLoading: false })
    mockUseRuns.mockReturnValue({ data: { items: [makeRun({ status: 'failed', created_at: new Date().toISOString() })] }, isLoading: false })
    mockUseProjects.mockReturnValue({ data: [], isLoading: false })
    render(<DashboardPage />, { wrapper: Wrapper })

    const totalCard = screen.getByText('流水线总数').closest('.ant-statistic')
    expect(totalCard?.textContent).toContain('2')
    const failedCard = screen.getByText('失败').closest('.ant-statistic')
    expect(failedCard?.textContent).toContain('1')
  })
})
