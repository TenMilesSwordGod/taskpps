import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
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

vi.mock('@/api/runs', () => ({
  useRuns: (params?: unknown) => mockUseRuns(params),
  useDeleteRun: () => mockUseDeleteRun(),
  useCleanRuns: () => mockUseCleanRuns(),
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
    mockUseCleanRuns.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
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
