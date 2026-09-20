/**
 * PipelineListPage UX 补测（2026-09，QA 审计）。
 *
 * 覆盖维度：错误态 / 空态引导 / 搜索无结果出路 / 无障碍 / 加载态。
 * 背景：功能用例已覆盖分组、展开、删除、新建弹窗入口；本文件补 UX 缺口，
 * 其中 `it.fails` 为已确认缺陷（修复后 vitest 报 unexpected pass，改回 it）。
 * v2 (2026-09, issue #215/#218/#219): 缺陷已修复，用例已转为常规断言。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import PipelineListPage from '../PipelineListPage'
import type { PipelineSummary } from '@/types'

function makePipeline(overrides: Partial<PipelineSummary> = {}): PipelineSummary {
  return {
    name: 'demo',
    file: 'demo.yaml',
    folder: '',
    project_id: 'proj-1',
    project_name: 'Demo',
    task_count: 3,
    subpipeline_count: 1,
    last_run: null,
    last_operator: null,
    last_operator_nickname: null,
    success_rate: 0.8,
    recent_runs: [],
    valid: true,
    validation_error: null,
    ...overrides,
  }
}

const mockUsePipelines = vi.fn()
vi.mock('@/api/pipelines', () => ({
  usePipelines: () => mockUsePipelines(),
  useDeletePipeline: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteFolder: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('../components/CreatePipelineModal', () => ({ default: () => null }))
vi.mock('../components/CreateFolderModal', () => ({ default: () => null }))
vi.mock('../components/RegisterProjectModal', () => ({ default: () => null }))
vi.mock('../components/RenameModal', () => ({ default: () => null }))
vi.mock('../components/SuccessRateChart', () => ({ default: () => <span data-testid="rate-chart" /> }))
vi.mock('@/components/StatusTag', () => ({
  default: ({ status }: { status: string }) => <span data-testid="status-tag">{status}</span>,
}))
vi.mock('@/components/TriggerRunModal', () => ({ default: () => null }))

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
  mockUsePipelines.mockReset()
})

describe('<PipelineListPage /> UX-错误态', () => {
  it('UX-流水线列表请求失败时展示错误与重试，而不是伪装成空列表', async () => {
    mockUsePipelines.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('500 Internal Server Error'),
      refetch: vi.fn(),
    })
    render(<PipelineListPage />, { wrapper: Wrapper })

    expect(await screen.findByText(/加载失败|无法获取|请求失败/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
    expect(screen.queryByText('暂无数据')).not.toBeInTheDocument()
  })
})

describe('<PipelineListPage /> UX-空态', () => {
  it('UX-无流水线时展示新建/注册引导，而不是默认「暂无数据」', () => {
    mockUsePipelines.mockReturnValue({ data: { items: [], folders: [] }, isLoading: false, refetch: vi.fn() })
    render(<PipelineListPage />, { wrapper: Wrapper })

    expect(screen.getByText(/还没有流水线|暂无流水线/)).toBeInTheDocument()
    const emptyArea = document.querySelector('.ant-empty')
    expect(emptyArea?.querySelector('button, a')).not.toBeNull()
  })

  it('UX-搜索无结果时展示「无匹配的流水线」并提供清除搜索入口', async () => {
    mockUsePipelines.mockReturnValue({
      data: { items: [makePipeline()], folders: [] },
      isLoading: false,
      refetch: vi.fn(),
    })
    render(<PipelineListPage />, { wrapper: Wrapper })

    await userEvent.type(screen.getByPlaceholderText('搜索流水线名称或文件'), '不存在的流水线')
    expect(await screen.findByText(/无匹配的流水线|无匹配流水线/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /清除搜索|清除筛选|重置/ })).toBeInTheDocument()
  })
})

describe('<PipelineListPage /> UX-无障碍', () => {
  it('UX-行内「触发运行」仅图标按钮具有可访问名称', () => {
    mockUsePipelines.mockReturnValue({
      data: { items: [makePipeline()], folders: [] },
      isLoading: false,
      refetch: vi.fn(),
    })
    render(<PipelineListPage />, { wrapper: Wrapper })

    // 必须限定在表格内，避免工具栏上带文字的「触发运行」按钮让断言假通过
    const table = screen.getByRole('table')
    expect(within(table).getByRole('button', { name: '触发运行' })).toBeInTheDocument()
  })
})

describe('<PipelineListPage /> UX-加载态', () => {
  it('UX-首次加载时表格展示 loading', () => {
    mockUsePipelines.mockReturnValue({ data: undefined, isLoading: true, refetch: vi.fn() })
    const { container } = render(<PipelineListPage />, { wrapper: Wrapper })

    expect(container.querySelector('.ant-spin')).not.toBeNull()
  })
})
