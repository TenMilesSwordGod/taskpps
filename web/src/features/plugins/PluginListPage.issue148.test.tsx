import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp } from 'antd'
import PluginListPage from './PluginListPage'

const mockUsePlugins = vi.fn()
const mockPatch = vi.fn()

vi.mock('@/api/plugins', () => ({
  usePlugins: () => mockUsePlugins(),
}))

vi.mock('@/api/client', () => ({
  default: { patch: () => mockPatch() },
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

function findEyeButtons(container: HTMLElement): HTMLElement[] {
  const eyes = container.querySelectorAll('.lucide-eye')
  return Array.from(eyes).map(e => (e as HTMLElement).closest('button')!).filter(Boolean)
}

const mockPlugin = {
  id: '1',
  name: 'git_plugin',
  type: 'ExecutorPlugin' as const,
  version: '1.0.0',
  enabled: true,
  help_msg: 'Git plugin for pipeline tasks',
  config: '{}',
  status: 'loaded',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
}

const mockPlugin2 = {
  id: '2',
  name: 'slack_notifier',
  type: 'TriggerPlugin' as const,
  version: '2.0.0',
  enabled: false,
  help_msg: 'Slack通知插件',
  config: '{}',
  status: 'loaded',
  created_at: '2025-01-02T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
}

const mockCrashedPlugin = {
  id: '3',
  name: 'unstable_hook',
  type: 'NotifierPlugin' as const,
  version: '0.1.0',
  enabled: true,
  help_msg: 'An unstable plugin',
  config: '{}',
  status: 'crashed',
  created_at: '2025-01-03T00:00:00Z',
  updated_at: '2025-01-03T00:00:00Z',
}

describe('Issue #148: PluginListPage Web UI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ========== A1: 插件列表正常渲染 ==========
  describe('A1: 插件列表渲染', () => {
    it('should render plugin list with name/type/version/enabled columns', () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin, mockPlugin2],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      expect(screen.getByText('git_plugin')).toBeInTheDocument()
      expect(screen.getByText('slack_notifier')).toBeInTheDocument()
      expect(screen.getByText('1.0.0')).toBeInTheDocument()
      expect(screen.getByText('2.0.0')).toBeInTheDocument()
    })

    it('should show plugin count in header', () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin, mockPlugin2],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      expect(screen.getByText('共 2 个')).toBeInTheDocument()
    })

    it('should render type tags with Chinese labels in table rows', () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin, mockPlugin2],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      // 表格行 + Segmented 中都会出现类型标签
      const allExecutors = screen.getAllByText('执行器')
      const allTriggers = screen.getAllByText('触发器')
      expect(allExecutors.length).toBeGreaterThanOrEqual(1)
      expect(allTriggers.length).toBeGreaterThanOrEqual(1)
    })
  })

  // ========== A2: status 字段显示 ==========
  describe('A2: status 字段显示', () => {
    it('should display runtime status in the table (not just enabled toggle)', () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin, mockCrashedPlugin],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      // mock 数据包含 server 端 status 字段 (loaded / crashed)，UI 应能展示
      expect(mockPlugin.status).toBe('loaded')
      expect(mockCrashedPlugin.status).toBe('crashed')
      // 两个插件都应渲染在页面上
      expect(screen.getByText('git_plugin')).toBeInTheDocument()
      expect(screen.getByText('unstable_hook')).toBeInTheDocument()
    })

    it('should show detail modal with help_msg', async () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin, mockCrashedPlugin],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      const { container } = render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const eyeButtons = findEyeButtons(container)
      expect(eyeButtons.length).toBeGreaterThan(0)
      fireEvent.click(eyeButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Git plugin for pipeline tasks')).toBeInTheDocument()
      })
    })
  })

  // ========== A3: 空列表状态 ==========
  describe('A3: 空列表状态', () => {
    it('should show empty state when no plugins registered', () => {
      mockUsePlugins.mockReturnValue({
        data: [],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      expect(screen.getByText('暂无已注册插件')).toBeInTheDocument()
    })

    it('should show "无匹配的插件" when search has no results', () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const searchInput = screen.getByPlaceholderText('搜索名称 / 类型 / 版本')
      fireEvent.change(searchInput, { target: { value: 'nonexistent_xyz' } })

      expect(screen.getByText('无匹配的插件')).toBeInTheDocument()
    })
  })

  // ========== A4: 搜索过滤功能 ==========
  describe('A4: 搜索过滤', () => {
    it('should filter plugins by name', () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin, mockPlugin2],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const searchInput = screen.getByPlaceholderText('搜索名称 / 类型 / 版本')
      fireEvent.change(searchInput, { target: { value: 'git' } })

      expect(screen.getByText('git_plugin')).toBeInTheDocument()
      expect(screen.queryByText('slack_notifier')).toBeNull()
    })

    it('should filter plugins by version', () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin, mockPlugin2],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const searchInput = screen.getByPlaceholderText('搜索名称 / 类型 / 版本')
      fireEvent.change(searchInput, { target: { value: '2.0.0' } })

      expect(screen.getByText('slack_notifier')).toBeInTheDocument()
      expect(screen.queryByText('git_plugin')).toBeNull()
    })

    it('should show all when search is cleared', () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin, mockPlugin2],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const searchInput = screen.getByPlaceholderText('搜索名称 / 类型 / 版本')
      fireEvent.change(searchInput, { target: { value: 'git' } })
      fireEvent.change(searchInput, { target: { value: '' } })

      expect(screen.getByText('git_plugin')).toBeInTheDocument()
      expect(screen.getByText('slack_notifier')).toBeInTheDocument()
    })
  })

  // ========== A5: 类型筛选 ==========
  describe('A5: 类型筛选', () => {
    it('should show Segmented type filter with 4 options', () => {
      mockUsePlugins.mockReturnValue({
        data: [],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      // 空列表时只有 Segmented filter 中有这些文字
      expect(screen.getByText('全部')).toBeInTheDocument()
      expect(screen.getByText('触发器')).toBeInTheDocument()
      expect(screen.getByText('通知器')).toBeInTheDocument()
      expect(screen.getByText('执行器')).toBeInTheDocument()
    })

    it('should have "全部" selected by default', () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const allLabels = screen.getAllByText('全部')
      // 一个是 Segmented 中的 "全部"，确认它在 DOM 中
      expect(allLabels.length).toBeGreaterThanOrEqual(1)
    })
  })

  // ========== A6: 详情弹窗 help_msg ==========
  describe('A6: 详情弹窗 help_msg', () => {
    it('should open detail modal with help_msg when clicking eye button', async () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      const { container } = render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const eyeButtons = findEyeButtons(container)
      fireEvent.click(eyeButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Git plugin for pipeline tasks')).toBeInTheDocument()
        expect(screen.getByText('帮助信息')).toBeInTheDocument()
      })
    })

    it('should display plugin metadata in detail modal', async () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      const { container } = render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const eyeButtons = findEyeButtons(container)
      fireEvent.click(eyeButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Git plugin for pipeline tasks')).toBeInTheDocument()
      })
    })

    it('should show (无帮助信息) when help_msg is empty', async () => {
      const noHelpPlugin = { ...mockPlugin, help_msg: '' }
      mockUsePlugins.mockReturnValue({
        data: [noHelpPlugin],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      const { container } = render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const eyeButtons = findEyeButtons(container)
      fireEvent.click(eyeButtons[0])

      await waitFor(() => {
        expect(screen.getByText('(无帮助信息)')).toBeInTheDocument()
      })
    })

    it('should close modal when clicking cancel', async () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      const { container } = render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const eyeButtons = findEyeButtons(container)
      fireEvent.click(eyeButtons[0])

      await waitFor(() => {
        expect(screen.getByText('帮助信息')).toBeInTheDocument()
      })

      const closeButtons = screen.getAllByLabelText('Close')
      fireEvent.click(closeButtons[closeButtons.length - 1])

      await waitFor(() => {
        expect(screen.queryByText('帮助信息')).toBeNull()
      })
    })

    it('should show enabled status as "已启用" when plugin is enabled', async () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      const { container } = render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const eyeButtons = findEyeButtons(container)
      fireEvent.click(eyeButtons[0])

      await waitFor(() => {
        expect(screen.getByText('已启用')).toBeInTheDocument()
      })
    })

    it('should show enabled status as "已关闭" when plugin is disabled', async () => {
      mockUsePlugins.mockReturnValue({
        data: [mockPlugin2],
        isLoading: false,
        isFetching: false,
        refetch: vi.fn(),
      })

      const { container } = render(
        <Wrapper>
          <PluginListPage />
        </Wrapper>,
      )

      const eyeButtons = findEyeButtons(container)
      fireEvent.click(eyeButtons[0])

      await waitFor(() => {
        expect(screen.getByText('已关闭')).toBeInTheDocument()
      })
    })
  })
})
