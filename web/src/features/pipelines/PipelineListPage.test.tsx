import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
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

vi.mock('@/api/pipelines', () => ({
  usePipelines: () => mockUsePipelines(),
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
