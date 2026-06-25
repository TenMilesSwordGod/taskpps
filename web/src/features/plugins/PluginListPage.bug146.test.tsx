import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp } from 'antd'
import PluginListPage from './PluginListPage'

const mockUsePlugins = vi.fn()

vi.mock('@/api/plugins', () => ({
  usePlugins: () => mockUsePlugins(),
}))

vi.mock('@/api/client', () => ({
  default: { patch: vi.fn() },
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>{children}</AntdApp>
    </QueryClientProvider>
  )
}

describe('Bug #146: PluginListPage TYPE_FILTER_OPTIONS i18n', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUsePlugins.mockReturnValue({
      data: [],
      isLoading: false,
      isFetching: false,
      refetch: vi.fn(),
    })
  })

  it('should render Chinese labels for type filter segmented options', () => {
    render(
      <Wrapper>
        <PluginListPage />
      </Wrapper>,
    )

    expect(screen.getByText('全部')).toBeInTheDocument()
    expect(screen.getByText('触发器')).toBeInTheDocument()
    expect(screen.getByText('通知器')).toBeInTheDocument()
    expect(screen.getByText('执行器')).toBeInTheDocument()
  })

  it('should NOT render English type names in the segmented filter', () => {
    render(
      <Wrapper>
        <PluginListPage />
      </Wrapper>,
    )

    expect(screen.queryByText('TriggerPlugin')).toBeNull()
    expect(screen.queryByText('NotifierPlugin')).toBeNull()
    expect(screen.queryByText('ExecutorPlugin')).toBeNull()
  })

  it('should show empty state when no plugins registered', () => {
    render(
      <Wrapper>
        <PluginListPage />
      </Wrapper>,
    )

    expect(screen.getByText('暂无已注册插件')).toBeInTheDocument()
  })
})
