import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import type { RunResponse } from '@/types'

/*
 * 捕获 Table 的 pagination.onChange / onShowSizeChange 回调，
 * 以便在测试中直接验证 pageSize 状态管理是否正确更新，
 * 绕过 JSDOM 中 rc-virtual-list 无法渲染 Select 下拉选项的局限。
 */
let capturedOnChange: ((page: number, pageSize: number) => void) | null = null
let capturedOnShowSizeChange: ((current: number, size: number) => void) | null = null

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd')
  const ActualTable = actual.Table
  const MockTable = ((props: Record<string, unknown>) => {
    const pagination = props.pagination as Record<string, unknown> | undefined
    if (pagination) {
      if (!capturedOnChange) capturedOnChange = pagination.onChange as (p: number, ps: number) => void
      if (!capturedOnShowSizeChange) capturedOnShowSizeChange = pagination.onShowSizeChange as (c: number, s: number) => void
    }
    return <ActualTable {...props} />
  }) as typeof ActualTable
  MockTable.displayName = 'MockTable'
  return { ...actual, Table: MockTable }
})

import RunListPage from './RunListPage'

function makeRun(i: number): RunResponse {
  return {
    id: `run-${i}`,
    display_name: `run-${i}`,
    pipeline_name: 'demo',
    pipeline_file: 'demo.yaml',
    definition_id: 'abc123def456',
    project_id: null,
    project_name: null,
    status: 'success',
    error: null,
    started_at: '2026-01-01T00:00:00Z',
    finished_at: '2026-01-01T00:01:00Z',
    created_at: '2026-01-01T00:00:00Z',
    params: {},
    env: {},
    tasks: [],
  }
}

const mockUseRuns = vi.fn()
const mockMutateAsync = vi.fn()
const mockUseDeleteRun = vi.fn()
const mockUseCleanRuns = vi.fn()
const mockUseRunStats = vi.fn()

vi.mock('@/api/runs', () => ({
  useRuns: () => mockUseRuns(),
  useDeleteRun: () => mockUseDeleteRun(),
  useCleanRuns: () => mockUseCleanRuns(),
  useRunStats: () => mockUseRunStats(),
}))

vi.mock('@/components/StatusTag', () => ({
  default: ({ status }: { status: string }) => <span>{status}</span>,
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

describe('Bug #49', () => {
  beforeEach(() => {
    mockUseRuns.mockReset()
    mockUseDeleteRun.mockReset()
    mockUseCleanRuns.mockReset()
    mockUseRunStats.mockReset()
    mockUseDeleteRun.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    mockUseCleanRuns.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    mockUseRunStats.mockReturnValue({ data: { total: 0, pending: 0, running: 0, success: 0, failed: 0, cancelled: 0, partial: 0 } })
    capturedOnChange = null
    capturedOnShowSizeChange = null
  })

  it('切换每页条数应生效，不应跳回 12', async () => {
    const items = Array.from({ length: 50 }, (_, i) => makeRun(i + 1))
    mockUseRuns.mockReturnValue({ data: { items, total: 50 } })

    render(<RunListPage />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getByText('run-1')).toBeTruthy())

    // 默认 pageSize=12，第 1 页显示 run-1 ~ run-12
    expect(screen.getByText('run-12')).toBeTruthy()
    expect(screen.queryByText('run-13')).toBeNull()

    // 验证 pagination 回调已被组件传入
    expect(capturedOnChange).toBeTruthy()
    expect(capturedOnShowSizeChange).toBeTruthy()

    /*
     * 通过 pagination.onShowSizeChange 模拟用户切换每页条数为 24。
     * 组件用 useState 管理 pageSize，该回调调用 setPageSize(24)，
     * 触发 re-render 后 Table 的 pageSize 应为 24。
     */
    await act(async () => {
      capturedOnShowSizeChange!(1, 24)
    })

    // pageSize=24 后，第 1 页应显示 run-1 ~ run-24，而非被重置回 12
    await waitFor(() => expect(screen.getByText('run-24')).toBeTruthy())
    expect(screen.queryByText('run-25')).toBeNull()

    // 分页总数从 ceil(50/12)=5 减为 ceil(50/24)=3
    const pageItems = document.querySelectorAll('.ant-pagination-item')
    expect(pageItems.length).toBeLessThanOrEqual(3)
  })


})
