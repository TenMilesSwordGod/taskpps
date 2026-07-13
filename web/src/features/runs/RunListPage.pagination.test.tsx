import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import RunListPage from './RunListPage'
import type { RunResponse } from '@/types'

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

describe('RunListPage pagination', () => {
  beforeEach(() => {
    mockUseRuns.mockReset()
    mockUseDeleteRun.mockReset()
    mockUseCleanRuns.mockReset()
    mockUseRunStats.mockReset()
  })

  it('可以切换到第 2 页', async () => {
    const items = Array.from({ length: 30 }, (_, i) => makeRun(i + 1))
    mockUseRuns.mockReturnValue({ data: { items, total: 30 } })
    mockUseRunStats.mockReturnValue({ data: {} })
    mockUseDeleteRun.mockReturnValue({ mutateAsync: mockMutateAsync })
    mockUseCleanRuns.mockReturnValue({ mutateAsync: mockMutateAsync, isPending: false })

    render(<RunListPage />, { wrapper: Wrapper })

    await waitFor(() => expect(screen.getByText('run-1')).toBeTruthy())

    // 第 1 页显示 run-1..run-12
    expect(screen.queryByText('run-13')).toBeNull()

    // 点击第 2 页
    const page2 = screen.getByTitle('2') as HTMLElement
    fireEvent.click(page2)

    await waitFor(() => expect(screen.getByText('run-13')).toBeTruthy())
    expect(screen.queryByText('run-1')).toBeNull()
  })
})
