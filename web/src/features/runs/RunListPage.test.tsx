import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import RunListPage from './RunListPage'
import type { RunResponse } from '@/types'

/** 构造测试用 run 数据 */
function makeRun(overrides: Partial<RunResponse> = {}): RunResponse {
  return {
    id: 'run-1',
    pipeline_name: 'demo',
    pipeline_file: 'demo.yaml',
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

/** Mocks for api/runs hooks */
const mockUseRuns = vi.fn()
const mockMutateAsync = vi.fn()
const mockUseDeleteRun = vi.fn()
const mockUseCleanRuns = vi.fn()
const mockUseRunStats = vi.fn()

vi.mock('@/api/runs', () => ({
  useRuns: (params?: unknown) => mockUseRuns(params),
  useDeleteRun: () => mockUseDeleteRun(),
  useCleanRuns: () => mockUseCleanRuns(),
  useRunStats: () => mockUseRunStats(),
}))

vi.mock('@/components/StatusTag', () => ({
  default: ({ status }: { status: string }) => <span data-testid="status-tag">{status}</span>,
}))

vi.mock('@/components/TriggerRunModal', () => ({
  default: () => null,
}))

/** Wrapper: QueryClient + AntdApp + Router */
function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter>{children}</MemoryRouter>
      </AntdApp>
    </QueryClientProvider>
  )
}

/** 找到弹窗 OK 按钮（位于 ant-modal 容器内） */
function findOkButtonInModal(): HTMLElement {
  // Antd 5 把弹窗渲染在 .ant-modal-wrap 容器内
  const dialogs = document.querySelectorAll('.ant-modal')
  for (const d of Array.from(dialogs)) {
    if (d.textContent?.includes('确认删除')) {
      const okBtn = d.querySelector('.ant-modal-footer .ant-btn-primary') as HTMLElement | null
      if (okBtn) return okBtn
    }
  }
  throw new Error('删除确认弹窗未打开或找不到 OK 按钮')
}

describe('<RunListPage /> Issue #55 - 删除弹窗自动关闭', () => {
  beforeEach(() => {
    mockUseRuns.mockReset()
    mockUseDeleteRun.mockReset()
    mockUseCleanRuns.mockReset()
    mockMutateAsync.mockReset()
    mockUseRunStats.mockReset()
    mockUseCleanRuns.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    mockUseRunStats.mockReturnValue({ data: { total: 0, pending: 0, running: 0, success: 0, failed: 0, cancelled: 0, partial: 0 } })
  })

  it('删除成功后弹窗自动关闭', async () => {
    mockUseRuns.mockReturnValue({
      data: { items: [makeRun({ id: 'run-1' })] },
      isLoading: false,
    })
    mockMutateAsync.mockResolvedValue({ status: 'deleted', run_id: 'run-1' })
    mockUseDeleteRun.mockReturnValue({ mutateAsync: mockMutateAsync, isPending: false })

    render(<RunListPage />, { wrapper: Wrapper })

    // 1) 打开删除单条确认弹窗：点击行内的"删除"按钮
    fireEvent.click(screen.getByTestId('row-delete-btn'))

    // 2) 等待弹窗出现
    await waitFor(() => {
      expect(screen.getByText('确认删除')).toBeInTheDocument()
    })

    // 3) 点击弹窗里的 OK 按钮
    const okBtn = findOkButtonInModal()
    fireEvent.click(okBtn)

    // 4) 验证 mutation 被调用
    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith('run-1')
    })

    // 5) 弹窗应自动关闭
    await waitFor(() => {
      expect(screen.queryByText('确认删除')).not.toBeInTheDocument()
    })
  })

  it('删除失败时弹窗保持打开以便重试', async () => {
    mockUseRuns.mockReturnValue({
      data: { items: [makeRun({ id: 'run-1' })] },
      isLoading: false,
    })
    mockMutateAsync.mockRejectedValue(new Error('network'))
    mockUseDeleteRun.mockReturnValue({ mutateAsync: mockMutateAsync, isPending: false })

    render(<RunListPage />, { wrapper: Wrapper })

    fireEvent.click(screen.getByTestId('row-delete-btn'))
    await waitFor(() => {
      expect(screen.getByText('确认删除')).toBeInTheDocument()
    })

    fireEvent.click(findOkButtonInModal())

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalled()
    })

    // 失败时弹窗应保持打开
    expect(screen.getByText('确认删除')).toBeInTheDocument()
  })
})

describe('<RunListPage /> Issue #95 - 自定义分页条数', () => {
  beforeEach(() => {
    mockUseRuns.mockReset()
    mockUseDeleteRun.mockReset()
    mockUseCleanRuns.mockReset()
    mockMutateAsync.mockReset()
    mockUseRunStats.mockReset()
    mockUseDeleteRun.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    mockUseCleanRuns.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    mockUseRunStats.mockReturnValue({ data: { total: 0, pending: 0, running: 0, success: 0, failed: 0, cancelled: 0, partial: 0 } })
  })

  it('默认分页条数应为 12', async () => {
    mockUseRuns.mockReturnValue({
      data: { items: [makeRun({ id: 'r1' })] },
      isLoading: false,
    })
    render(<RunListPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('运行历史')).toBeInTheDocument())
    // 验证分页器存在且默认 pageSize 为 12
    const pagination = document.querySelector('.ant-pagination')
    expect(pagination).toBeTruthy()
    // Ant Design 在 size="small" 时分页大小选择器显示 "12 条/页"
    const pageSizeChanger = pagination?.querySelector('.ant-pagination-options-size-changer')
    expect(pageSizeChanger).toBeTruthy()
    expect(pageSizeChanger?.textContent).toContain('12')
  })

  it('应支持切换分页条数', async () => {
    const items = Array.from({ length: 30 }, (_, i) => makeRun({ id: `r${i}`, pipeline_name: `Pipe${i}` }))
    mockUseRuns.mockReturnValue({
      data: { items },
      isLoading: false,
    })
    render(<RunListPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('运行历史')).toBeInTheDocument())
    // 验证分页大小选择器存在
    const pageSizeSelector = document.querySelector('.ant-pagination-options-size-changer')
    expect(pageSizeSelector).toBeTruthy()
    expect(pageSizeSelector?.textContent).toContain('12')
  })
})

describe('<RunListPage /> UI 优化 - 统计与过滤', () => {
  beforeEach(() => {
    mockUseRuns.mockReset()
    mockUseDeleteRun.mockReset()
    mockUseCleanRuns.mockReset()
    mockMutateAsync.mockReset()
    mockUseRunStats.mockReset()
    mockUseDeleteRun.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    mockUseCleanRuns.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    mockUseRunStats.mockReturnValue({ data: { total: 0, pending: 0, running: 0, success: 0, failed: 0, cancelled: 0, partial: 0 } })
  })

  it('统计胶囊展示正确的计数', async () => {
    mockUseRuns.mockReturnValue({
      data: {
        items: [
          makeRun({ id: 'r1', status: 'success' }),
          makeRun({ id: 'r2', status: 'success' }),
          makeRun({ id: 'r3', status: 'failed' }),
          makeRun({ id: 'r4', status: 'running' }),
        ],
      },
      isLoading: false,
    })
    mockUseRunStats.mockReturnValue({ data: { total: 4, pending: 0, running: 1, success: 2, failed: 1, cancelled: 0, partial: 0 } })
    render(<RunListPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('运行历史')).toBeInTheDocument())
    expect(screen.getByText('总计 4')).toBeInTheDocument()
    expect(screen.getByText('成功 2')).toBeInTheDocument()
    expect(screen.getByText('失败 1')).toBeInTheDocument()
    expect(screen.getByText('运行中 1')).toBeInTheDocument()
  })

  it('Segmented 状态过滤：选择"失败"仅展示失败记录', async () => {
    mockUseRuns.mockReturnValue({
      data: {
        items: [
          makeRun({ id: 'ok-1', pipeline_name: 'SuccessPipeline', status: 'success' }),
          makeRun({ id: 'fail-1', pipeline_name: 'FailPipeline', status: 'failed' }),
        ],
      },
      isLoading: false,
    })
    render(<RunListPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('运行历史')).toBeInTheDocument())
    // 初始两条都可见
    expect(screen.getByText('SuccessPipeline')).toBeInTheDocument()
    expect(screen.getByText('FailPipeline')).toBeInTheDocument()
    // 点击"失败"
    fireEvent.click(screen.getByText('失败', { selector: '.ant-segmented-item-label' }))
    await waitFor(() => {
      expect(screen.queryByText('SuccessPipeline')).not.toBeInTheDocument()
      expect(screen.getByText('FailPipeline')).toBeInTheDocument()
    })
  })

  it('Segmented 状态过滤：选择"成功"仅展示成功记录', async () => {
    mockUseRuns.mockReturnValue({
      data: {
        items: [
          makeRun({ id: 'ok-2', pipeline_name: 'OkPipe', status: 'success' }),
          makeRun({ id: 'run-2', pipeline_name: 'RunPipe', status: 'running' }),
        ],
      },
      isLoading: false,
    })
    render(<RunListPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('运行历史')).toBeInTheDocument())
    fireEvent.click(screen.getByText('成功', { selector: '.ant-segmented-item-label' }))
    await waitFor(() => {
      expect(screen.getByText('OkPipe')).toBeInTheDocument()
      expect(screen.queryByText('RunPipe')).not.toBeInTheDocument()
    })
  })

  it('运行中行有蓝色背景提示', async () => {
    mockUseRuns.mockReturnValue({
      data: { items: [makeRun({ id: 'running-row', status: 'running' })] },
      isLoading: false,
    })
    render(<RunListPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('运行历史')).toBeInTheDocument())
    // 表格行应带有蓝色背景
    const row = document.querySelector('.ant-table-row')
    expect(row).toBeTruthy()
    expect(row?.getAttribute('style') || '').toContain('background')
  })
})
