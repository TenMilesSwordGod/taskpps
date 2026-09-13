/**
 * RunListPage UX 补测（2026-09，QA 审计）。
 *
 * 覆盖维度：错误态 / 空态（区分无数据与筛选无结果）/ 键盘可达 / 加载反馈。
 * 背景：功能用例（RunListPage.test / pagination / bug49）已覆盖删除、分页、筛选过滤，
 * 但「请求失败伪装空表」「无数据无引导」「筛选无结果无出路」「运行名不可键盘聚焦」
 * 等体验缺口零覆盖，故新增本文件。
 *
 * 注意：`it.fails` 标记已确认的 UX 缺陷（修复后 vitest 报 unexpected pass，改回 it）。
 * v2 (2026-09, issue #215/#218/#219): 缺陷已修复，用例已转为常规断言。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import RunListPage from '../RunListPage'
import type { RunResponse } from '@/types'

function makeRun(overrides: Partial<RunResponse> = {}): RunResponse {
  return {
    id: 'run-1',
    display_name: 'deploy-run',
    pipeline_name: 'demo',
    pipeline_file: 'demo.yaml',
    definition_id: 'abc123def456',
    project_id: null,
    status: 'success',
    error: null,
    started_at: '2026-01-01T00:00:00Z',
    finished_at: '2026-01-01T00:01:00Z',
    created_at: '2026-01-01T00:00:00Z',
    params: {},
    env: {},
    tasks: [],
    ...overrides,
  }
}

const mockUseRuns = vi.fn()
const mockRefetch = vi.fn()
const mockUseRunStats = vi.fn()
const mockCleanRuns = vi.fn()
const mockDeleteRun = vi.fn()

vi.mock('@/api/runs', () => ({
  useRuns: () => mockUseRuns(),
  useRunStats: () => mockUseRunStats(),
  useCleanRuns: () => mockCleanRuns(),
  useDeleteRun: () => mockDeleteRun(),
}))

vi.mock('@/components/StatusTag', () => ({
  default: ({ status }: { status: string }) => <span data-testid="status-tag">{status}</span>,
}))

vi.mock('@/components/PipelineProgressPopover', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('@/components/TriggerRunModal', () => ({
  default: () => null,
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
  mockRefetch.mockReset()
  mockUseRunStats.mockReset()
  mockCleanRuns.mockReset()
  mockDeleteRun.mockReset()
  mockUseRunStats.mockReturnValue({ data: { total: 0, pending: 0, running: 0, success: 0, failed: 0, cancelled: 0, partial: 0 } })
  mockCleanRuns.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
  mockDeleteRun.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
})

describe('<RunListPage /> UX-错误态', () => {
  it('UX-运行列表请求失败时展示错误提示与重试，而不是空白表格', async () => {
    mockUseRuns.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      error: new Error('500 Internal Server Error'),
      refetch: mockRefetch,
    })
    render(<RunListPage />, { wrapper: Wrapper })

    expect(await screen.findByText(/加载失败|无法获取|请求失败/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
  })
})

describe('<RunListPage /> UX-空态', () => {
  it('UX-无任何运行记录时展示明确的空态与触发运行引导（而非默认「暂无数据」）', () => {
    mockUseRuns.mockReturnValue({ data: { items: [] }, isLoading: false, isFetching: false, refetch: mockRefetch })
    render(<RunListPage />, { wrapper: Wrapper })

    expect(screen.getByText(/还没有运行记录|暂无运行记录/)).toBeInTheDocument()
    // 引导入口需位于空态容器内，避免误把工具栏按钮当作引导
    const emptyArea = document.querySelector('.ant-empty')
    expect(emptyArea?.querySelector('button, a')).not.toBeNull()
  })

  it('UX-筛选无结果时展示「无匹配运行」并提供清除筛选入口', async () => {
    mockUseRuns.mockReturnValue({
      data: { items: [makeRun({ display_name: 'deploy-run' })] },
      isLoading: false,
      isFetching: false,
      refetch: mockRefetch,
    })
    render(<RunListPage />, { wrapper: Wrapper })

    await userEvent.type(screen.getByPlaceholderText('搜索运行名称 / UUID / 项目 / 流水线'), '不存在的关键字')
    expect(await screen.findByText(/无匹配运行|无匹配记录/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /清除筛选|清除搜索|重置/ })).toBeInTheDocument()
  })
})

describe('<RunListPage /> UX-键盘可达', () => {
  it('UX-运行名是可聚焦链接（键盘可进入详情，而非仅鼠标点击）', () => {
    mockUseRuns.mockReturnValue({
      data: { items: [makeRun({ display_name: 'deploy-run' })] },
      isLoading: false,
      isFetching: false,
      refetch: mockRefetch,
    })
    render(<RunListPage />, { wrapper: Wrapper })

    const link = screen.getByRole('link', { name: 'deploy-run' })
    expect(link).toHaveAttribute('href', '/runs/run-1')
  })
})

describe('<RunListPage /> UX-加载反馈', () => {
  it('UX-刷新请求进行中刷新按钮禁用，防止重复刷新', () => {
    mockUseRuns.mockReturnValue({
      data: { items: [makeRun()] },
      isLoading: false,
      isFetching: true,
      refetch: mockRefetch,
    })
    render(<RunListPage />, { wrapper: Wrapper })

    expect(screen.getByRole('button', { name: /刷新/ })).toBeDisabled()
  })
})
