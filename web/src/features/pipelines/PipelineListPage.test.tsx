import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import PipelineListPage from './PipelineListPage'
import type { PipelineSummary } from '@/types'

function makePipeline(overrides: Partial<PipelineSummary> = {}): PipelineSummary {
  return {
    name: 'demo',
    file: 'demo.yaml',
    folder: '',
    project_id: null,
    project_name: null,
    task_count: 3,
    subpipeline_count: 1,
    last_run: null,
    success_rate: 0.8,
    ...overrides,
  }
}

const mockUsePipelines = vi.fn()
const mockDeletePipelineAsync = vi.fn()
const mockDeleteFolderAsync = vi.fn()

vi.mock('@/api/pipelines', () => ({
  usePipelines: () => mockUsePipelines(),
  useDeletePipeline: () => ({ mutateAsync: mockDeletePipelineAsync, isPending: false }),
  useDeleteFolder: () => ({ mutateAsync: mockDeleteFolderAsync, isPending: false }),
}))

// v3 (2026-09): 新建/重命名/注册弹窗在列表页仅验证「能否打开」，组件行为由各自单测覆盖
vi.mock('./components/CreatePipelineModal', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div data-testid="create-pipeline-modal" /> : null),
}))
vi.mock('./components/CreateFolderModal', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div data-testid="create-folder-modal" /> : null),
}))
vi.mock('./components/RegisterProjectModal', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div data-testid="register-project-modal" /> : null),
}))
vi.mock('./components/RenameModal', () => ({
  default: ({ open, kind }: { open: boolean; kind: string }) =>
    open ? <div data-testid={`rename-modal-${kind}`} /> : null,
}))

vi.mock('@/components/StatusTag', () => ({
  default: ({ status }: { status: string }) => <span data-testid="status-tag">{status}</span>,
}))

vi.mock('@/components/TriggerRunModal', () => ({
  default: () => null,
}))

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

describe('<PipelineListPage /> Issue #105 - 最近运行时间和状态分开', () => {
  beforeEach(() => {
    mockUsePipelines.mockReset()
  })

  it('pipeline 行有 last_run 时，"最近运行时间"列显示格式化时间，"最近运行状态"列显示状态标签', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({
            name: 'deploy',
            file: 'deploy.yaml',
            last_run: { id: 'run1', status: 'success', created_at: '2026-06-20T14:56:00+08:00' },
          }),
        ],
      },
      isLoading: false,
    })

    render(<PipelineListPage />, { wrapper: Wrapper })

    // 验证时间列显示格式化时间
    expect(screen.getByText('06-20 14:56')).toBeInTheDocument()

    // 验证状态列显示 StatusTag
    expect(screen.getByTestId('status-tag')).toHaveTextContent('success')
  })

  it('pipeline 行无 last_run 时，"最近运行时间"和"最近运行状态"列均显示 "-"', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({ name: 'deploy', file: 'deploy.yaml', last_run: null }),
        ],
      },
      isLoading: false,
    })

    render(<PipelineListPage />, { wrapper: Wrapper })

    // 表格中应有两个 "-"（时间列和状态列各一个）
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
  })

  it('非 pipeline 行（project/folder），"最近运行时间"和"最近运行状态"列均显示 "--"', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({ name: 'p1', file: 'p1.yaml', project_id: 'proj1', project_name: 'Proj1' }),
        ],
      },
      isLoading: false,
    })

    render(<PipelineListPage />, { wrapper: Wrapper })

    // project 行的两列都应显示 "--"
    const dashes = screen.getAllByText('--')
    expect(dashes.length).toBeGreaterThanOrEqual(2)
  })

  it('last_run 有 status 但无 created_at 时，时间列显示 "-"，状态列正常显示', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({
            name: 'deploy',
            file: 'deploy.yaml',
            last_run: { id: 'run2', status: 'failed', created_at: null },
          }),
        ],
      },
      isLoading: false,
    })

    render(<PipelineListPage />, { wrapper: Wrapper })

    // 状态列应显示 failed
    expect(screen.getByTestId('status-tag')).toHaveTextContent('failed')
  })
})

describe('<PipelineListPage /> Issue #105 - 额外边界场景测试', () => {
  beforeEach(() => {
    mockUsePipelines.mockReset()
  })

  it('多个 pipeline 行的时间和状态列各自独立显示', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({
            name: 'deploy',
            file: 'deploy.yaml',
            last_run: { id: 'run1', status: 'success', created_at: '2026-06-20T14:56:00+08:00' },
          }),
          makePipeline({
            name: 'test',
            file: 'test.yaml',
            last_run: { id: 'run2', status: 'failed', created_at: '2026-06-21T10:30:00+08:00' },
          }),
        ],
      },
      isLoading: false,
    })

    render(<PipelineListPage />, { wrapper: Wrapper })

    // 时间列：两个不同时间
    expect(screen.getByText('06-20 14:56')).toBeInTheDocument()
    expect(screen.getByText('06-21 10:30')).toBeInTheDocument()

    // 状态列：两个 StatusTag
    const statusTags = screen.getAllByTestId('status-tag')
    expect(statusTags.length).toBe(2)
    expect(statusTags[0]).toHaveTextContent('success')
    expect(statusTags[1]).toHaveTextContent('failed')
  })

  it('partial 状态正确显示为"部分完成"', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({
            name: 'deploy',
            file: 'deploy.yaml',
            last_run: { id: 'run1', status: 'partial', created_at: '2026-06-20T14:56:00+08:00' },
          }),
        ],
      },
      isLoading: false,
    })

    render(<PipelineListPage />, { wrapper: Wrapper })

    expect(screen.getByText('06-20 14:56')).toBeInTheDocument()
    expect(screen.getByTestId('status-tag')).toHaveTextContent('partial')
  })

  it('cancelled 状态正确显示为"已取消"', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({
            name: 'deploy',
            file: 'deploy.yaml',
            last_run: { id: 'run1', status: 'cancelled', created_at: '2026-06-20T14:56:00+08:00' },
          }),
        ],
      },
      isLoading: false,
    })

    render(<PipelineListPage />, { wrapper: Wrapper })

    expect(screen.getByTestId('status-tag')).toHaveTextContent('cancelled')
  })
})

describe('<PipelineListPage /> Issue #104 - 展开/折叠动画', () => {
  beforeEach(() => {
    mockUsePipelines.mockReset()
  })

  it('project 行显示带旋转动画的展开图标', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({ name: 'p1', file: 'p1.yaml', project_id: 'proj1', project_name: 'Proj1' }),
        ],
      },
      isLoading: false,
    })

    const { container } = render(<PipelineListPage />, { wrapper: Wrapper })

    // 找到展开图标
    const expandIcons = container.querySelectorAll('.pipeline-expand-icon')
    expect(expandIcons.length).toBeGreaterThanOrEqual(1)

    // 图标应有 transition 样式
    const icon = expandIcons[0] as HTMLElement
    expect(icon.style.transition).toContain('transform')
    expect(icon.style.transition).toContain('200ms')
  })

  it('点击展开图标切换展开状态，图标旋转角度变化', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({ name: 'p1', file: 'p1.yaml', project_id: 'proj1', project_name: 'Proj1' }),
          makePipeline({ name: 'p2', file: 'p2.yaml', project_id: 'proj1', project_name: 'Proj1' }),
        ],
      },
      isLoading: false,
    })

    const { container } = render(<PipelineListPage />, { wrapper: Wrapper })

    const expandIcons = container.querySelectorAll('.pipeline-expand-icon')
    expect(expandIcons.length).toBeGreaterThanOrEqual(1)

    const icon = expandIcons[0] as HTMLElement

    // 初始状态：默认展开（pipelineCount <= 10），应为 rotate(90deg)
    expect(icon.style.transform).toBe('rotate(90deg)')

    // 点击折叠
    fireEvent.click(icon)
    await waitFor(() => {
      expect(icon.style.transform).toBe('rotate(0deg)')
    })

    // 再次点击展开
    fireEvent.click(icon)
    await waitFor(() => {
      expect(icon.style.transform).toBe('rotate(90deg)')
    })
  })

  it('非可展开行不显示旋转图标', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({ name: 'p1', file: 'p1.yaml' }),
        ],
      },
      isLoading: false,
    })

    const { container } = render(<PipelineListPage />, { wrapper: Wrapper })

    // 单项目无 folder 时，pipeline 行不可展开
    const expandIcons = container.querySelectorAll('.pipeline-expand-icon')
    // 不应有 pipeline-expand-icon（pipeline 行显示空 span 占位）
    expect(expandIcons.length).toBe(0)
  })

  it('渲染展开行动画 CSS 样式', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({ name: 'p1', file: 'p1.yaml', project_id: 'proj1', project_name: 'Proj1' }),
        ],
      },
      isLoading: false,
    })

    render(<PipelineListPage />, { wrapper: Wrapper })

    // 检查 style 标签包含动画关键帧
    const styleTags = document.querySelectorAll('style')
    const hasAnimation = Array.from(styleTags).some((tag) =>
      tag.textContent?.includes('pipelineRowFadeIn'),
    )
    expect(hasAnimation).toBe(true)
  })
})

describe('<PipelineListPage /> 多项目展开/折叠 bug — 重复 file 导致 key 冲突', () => {
  beforeEach(() => {
    mockUsePipelines.mockReset()
  })

  it('多个项目含相同 file 的 pipeline 时，各项目可独立展开/折叠', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [
          makePipeline({ id: 'pipe-1', name: 'p1', file: 'example.yaml', project_id: 'proj1', project_name: 'Proj1' }),
          makePipeline({ id: 'pipe-2', name: 'p2', file: 'example.yaml', project_id: 'proj2', project_name: 'Proj2' }),
        ],
      },
      isLoading: false,
    })

    const { container } = render(<PipelineListPage />, { wrapper: Wrapper })

    // 等待 useEffect 初始展开（pipelineCount=1 ≤ 10）
    await waitFor(() => {
      expect(screen.getByText('p1')).toBeInTheDocument()
      expect(screen.getByText('p2')).toBeInTheDocument()
    })

    // 两个 project 行各有一个展开图标
    const expandIcons = container.querySelectorAll('.pipeline-expand-icon')
    expect(expandIcons.length).toBe(2)

    // 折叠第一个项目 → p1 应消失，p2 应保留
    fireEvent.click(expandIcons[0])
    await waitFor(() => {
      expect(screen.queryByText('p1')).not.toBeInTheDocument()
    })
    expect(screen.getByText('p2')).toBeInTheDocument()

    // 重新展开第一个项目 → p1 应回来
    fireEvent.click(expandIcons[0])
    await waitFor(() => {
      expect(screen.getByText('p1')).toBeInTheDocument()
    })
    expect(screen.getByText('p2')).toBeInTheDocument()
  })
})

// v3 (2026-09): 网页端新建流水线/文件夹/注册项目 + 重命名/删除入口
describe('<PipelineListPage /> v3 - 新建与行操作入口', () => {
  beforeEach(() => {
    mockUsePipelines.mockReset()
    mockDeletePipelineAsync.mockReset()
    mockDeleteFolderAsync.mockReset()
  })

  it('工具栏「新建」下拉包含新建流水线/文件夹/注册项目', async () => {
    mockUsePipelines.mockReturnValue({ data: { items: [], folders: [] }, isLoading: false })
    const user = userEvent.setup()
    render(<PipelineListPage />, { wrapper: Wrapper })

    // 注意(2026-09, issue #218): 空态现在也有「新建流水线」CTA，
    // 因此工具栏按钮用精确名「新建」，下拉项在菜单容器内断言，避免歧义
    await user.click(screen.getByRole('button', { name: '新建' }))
    const menu = await waitFor(() => {
      const el = document.querySelector('.ant-dropdown-menu')
      if (!el) throw new Error('下拉菜单未打开')
      return el as HTMLElement
    })
    expect(within(menu).getByText('新建流水线')).toBeInTheDocument()
    expect(within(menu).getByText('新建文件夹')).toBeInTheDocument()
    expect(within(menu).getByText('注册项目目录')).toBeInTheDocument()
  })

  it('点击「新建流水线」打开新建弹窗', async () => {
    mockUsePipelines.mockReturnValue({ data: { items: [], folders: [] }, isLoading: false })
    const user = userEvent.setup()
    render(<PipelineListPage />, { wrapper: Wrapper })

    await user.click(screen.getByRole('button', { name: '新建' }))
    const menu = await waitFor(() => {
      const el = document.querySelector('.ant-dropdown-menu')
      if (!el) throw new Error('下拉菜单未打开')
      return el as HTMLElement
    })
    await user.click(within(menu).getByText('新建流水线'))
    expect(await screen.findByTestId('create-pipeline-modal')).toBeInTheDocument()
  })

  it('后端返回的空文件夹渲染为 folder 行（可独立展开）', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [],
        folders: [{ project_id: 'proj1', folder: 'debug', project_name: 'Proj1' }],
      },
      isLoading: false,
    })
    render(<PipelineListPage />, { wrapper: Wrapper })

    await waitFor(() => {
      expect(screen.getByText('debug/')).toBeInTheDocument()
    })
    expect(screen.getByText('Proj1')).toBeInTheDocument()
  })

  it('folder 行「更多操作」提供重命名/删除', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [],
        folders: [{ project_id: 'proj1', folder: 'debug', project_name: 'Proj1' }],
      },
      isLoading: false,
    })
    const user = userEvent.setup()
    render(<PipelineListPage />, { wrapper: Wrapper })

    const moreBtn = await screen.findByLabelText('更多操作')
    await user.click(moreBtn)
    expect(await screen.findByText('重命名')).toBeInTheDocument()
    expect(screen.getByText('删除')).toBeInTheDocument()
  })

  it('点击 folder 行「重命名」打开重命名弹窗', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [],
        folders: [{ project_id: 'proj1', folder: 'debug', project_name: 'Proj1' }],
      },
      isLoading: false,
    })
    const user = userEvent.setup()
    render(<PipelineListPage />, { wrapper: Wrapper })

    await user.click(await screen.findByLabelText('更多操作'))
    await user.click(await screen.findByText('重命名'))
    expect(await screen.findByTestId('rename-modal-folder')).toBeInTheDocument()
  })

  it('确认删除流水线后调用删除接口', async () => {
    mockUsePipelines.mockReturnValue({
      data: {
        items: [makePipeline({ id: 'pipe-1', name: 'demo', file: 'demo.yaml', project_id: 'proj1', project_name: 'Proj1' })],
        folders: [],
      },
      isLoading: false,
    })
    mockDeletePipelineAsync.mockResolvedValue({ status: 'deleted' })
    const user = userEvent.setup()
    render(<PipelineListPage />, { wrapper: Wrapper })

    await user.click(await screen.findByLabelText('更多操作'))
    await user.click(await screen.findByText('删除'))
    // 确认弹窗的确定按钮（antd 会在两个中文字符间插入空格，用正则匹配）
    await user.click(await screen.findByRole('button', { name: /删\s*除/ }))

    await waitFor(() => {
      expect(mockDeletePipelineAsync).toHaveBeenCalledWith({ projectId: 'proj1', file: 'demo.yaml' })
    })
  })
})
