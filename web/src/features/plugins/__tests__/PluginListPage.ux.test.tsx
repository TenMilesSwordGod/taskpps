/**
 * PluginListPage UX 补测（2026-09，QA 审计）。
 *
 * 覆盖维度：错误态 / 操作反馈 / 提交防重 / 无障碍 / 加载态。
 * 背景：功能用例（PluginListPage.issue148 / bug146）已覆盖列表与过滤，
 * 但「请求失败伪装空态」「开关静默失败」「无防重复」「图标按钮无可访问名称」
 * 四个体验缺口零覆盖，故新增本文件。
 *
 * 注意：文件内 `it.fails` 标记的是审计确认的已知 UX 缺陷（缺陷清单见
 * .debug/qa-audit/report-web-ux-gaps.md），修复后 vitest 会报 "unexpected pass"，
 * 届时把 it.fails 改回 it 即可。
 * v2 (2026-09, issue #214): 缺陷已修复，全部用例已转为常规断言（it）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import PluginListPage from '../PluginListPage'
import type { PluginResponse } from '@/types'

const mockUsePlugins = vi.fn()
const mockRefetch = vi.fn()
vi.mock('@/api/plugins', () => ({
  usePlugins: () => mockUsePlugins(),
}))

const mockPatch = vi.fn()
vi.mock('@/api/client', () => ({
  default: {
    patch: (...args: unknown[]) => mockPatch(...args),
    get: vi.fn(),
  },
}))

vi.mock('../PluginDetailModal', () => ({
  default: () => null,
}))

function makePlugin(overrides: Partial<PluginResponse> = {}): PluginResponse {
  return {
    name: 'cron-trigger',
    type: 'TriggerPlugin',
    version: '1.0.0',
    enabled: true,
    status: 'loaded',
    ...overrides,
  }
}

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
  mockUsePlugins.mockReset()
  mockPatch.mockReset()
  mockRefetch.mockReset()
})

describe('<PluginListPage /> UX-加载态', () => {
  it('UX-插件加载中展示 loading（不显示空态）', () => {
    mockUsePlugins.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, refetch: mockRefetch })
    const { container } = render(<PluginListPage />, { wrapper: Wrapper })
    expect(container.querySelector('.ant-spin')).not.toBeNull()
    expect(screen.queryByText('暂无已注册插件')).not.toBeInTheDocument()
  })
})

describe('<PluginListPage /> UX-错误态', () => {
  it('UX-插件接口失败时展示错误提示与重试，而不是「暂无已注册插件」', async () => {
    mockUsePlugins.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
      error: new Error('500 Internal Server Error'),
      refetch: mockRefetch,
    })
    render(<PluginListPage />, { wrapper: Wrapper })

    expect(await screen.findByText(/加载失败|无法获取|请求失败/)).toBeInTheDocument()
    // 注意(2026-09): AntD 会给纯两字中文按钮插入空格（可访问名称为「重 试」），用 \s* 兼容
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
    expect(screen.queryByText('暂无已注册插件')).not.toBeInTheDocument()
  })
})

describe('<PluginListPage /> UX-开关反馈与防重', () => {
  it('UX-插件启用开关成功后给出可见反馈', async () => {
    mockUsePlugins.mockReturnValue({ data: [makePlugin()], isLoading: false, isFetching: false, refetch: mockRefetch })
    mockPatch.mockResolvedValue({ data: {} })
    render(<PluginListPage />, { wrapper: Wrapper })

    await userEvent.click(screen.getByRole('switch'))
    await waitFor(() => expect(mockPatch).toHaveBeenCalledWith('/api/plugins/cron-trigger/toggle'))
    expect(await screen.findByText(/切换成功|已启用|已开启|已关闭|已停用|操作成功/)).toBeInTheDocument()
  })

  it('UX-插件启用开关失败时提示错误，而不是仅 console.error', async () => {
    mockUsePlugins.mockReturnValue({ data: [makePlugin()], isLoading: false, isFetching: false, refetch: mockRefetch })
    mockPatch.mockRejectedValue(new Error('403 Forbidden'))
    render(<PluginListPage />, { wrapper: Wrapper })

    await userEvent.click(screen.getByRole('switch'))
    expect(await screen.findByText(/切换失败|操作失败|403/)).toBeInTheDocument()
  })

  it('UX-插件开关请求进行中禁止重复提交（双击只发一次 PATCH）', async () => {
    mockUsePlugins.mockReturnValue({ data: [makePlugin()], isLoading: false, isFetching: false, refetch: mockRefetch })
    // 永不 resolve：模拟慢请求
    mockPatch.mockReturnValue(new Promise(() => {}))
    render(<PluginListPage />, { wrapper: Wrapper })

    const switchEl = screen.getByRole('switch')
    await userEvent.click(switchEl)
    await userEvent.click(switchEl)

    expect(mockPatch).toHaveBeenCalledTimes(1)
    expect(switchEl).toBeDisabled()
  })
})

describe('<PluginListPage /> UX-无障碍', () => {
  it('UX-「查看详情」仅图标按钮具有可访问名称', () => {
    mockUsePlugins.mockReturnValue({ data: [makePlugin()], isLoading: false, isFetching: false, refetch: mockRefetch })
    render(<PluginListPage />, { wrapper: Wrapper })

    expect(screen.getByRole('button', { name: '查看详情' })).toBeInTheDocument()
  })
})
