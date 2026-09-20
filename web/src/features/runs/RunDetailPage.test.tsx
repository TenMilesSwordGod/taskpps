import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { App as AntdApp } from 'antd'

// Mocks（必须在 import 被测组件前声明）
const mockUseRun = vi.fn()
const mockUseCancelRun = vi.fn()
const mockUseRunConsole = vi.fn()
const mockUsePipelineSnapshot = vi.fn()
const mockUsePipeline = vi.fn()
const mockUseRetryVersions = vi.fn()
const mockUseResultPage = vi.fn()
const mockUseArtifacts = vi.fn()

vi.mock('@/api/runs', () => ({
  useRun: (id?: string) => mockUseRun(id),
  useCancelRun: () => mockUseCancelRun(),
  useRunConsole: () => mockUseRunConsole(),
  usePipelineSnapshot: (id?: string) => mockUsePipelineSnapshot(id),
  useRetryVersions: (id?: string) => mockUseRetryVersions(id),
  useResultPage: (id?: string) => mockUseResultPage(id),
  useArtifacts: (id?: string) => mockUseArtifacts(id),
}))

// usePipeline 不应被调用：#57 修复后禁止回退到当前 pipeline 文件
vi.mock('@/api/pipelines', () => ({
  usePipeline: (file?: string) => mockUsePipeline(file),
}))

vi.mock('@/components/StatusTag', () => ({
  default: ({ status }: { status: string }) => <span data-testid="status-tag">{status}</span>,
}))

// 捕获 TaskTree 收到的 pipeline，用于断言"用的是快照"
const mockTaskTreeProps = vi.fn()
vi.mock('./TaskTree', () => ({
  default: (props: Record<string, unknown>) => {
    mockTaskTreeProps(props)
    return (
      <div data-testid="task-tree" data-pipeline-id={(props.pipeline as { id?: string } | undefined)?.id ?? ''}>
        {/* 模拟真实 TaskTree 头部的收起按钮，验证页面把 onCollapse 接到了"收起"动作 */}
        {typeof props.onCollapse === 'function' && (
          <button data-testid="tree-collapse" aria-label="隐藏任务树" onClick={props.onCollapse as () => void} />
        )}
      </div>
    )
  },
}))

vi.mock('./LogViewer', () => ({
  default: () => <div data-testid="log-viewer" />,
}))

// Issue #113: 捕获 RunStagePanel 收到的 props，用于断言面板传入快照和任务运行记录
const mockRunStagePanelProps = vi.fn()
vi.mock('./ResultViewer', () => ({
  default: ({ data }: { data?: unknown }) => <div data-testid="result-viewer" data-has-data={String(!!data)} />,
}))

vi.mock('./RunStagePanel', () => ({
  default: (props: Record<string, unknown>) => {
    mockRunStagePanelProps(props)
    return <div data-testid="run-stage-panel" />
  },
}))

vi.mock('./hooks/useSSELogs', () => ({
  useSSELogs: () => ({
    logs: [],
    connected: false,
    clearLogs: vi.fn(),
    reconnect: vi.fn(),
  }),
}))

import RunDetailPage from './RunDetailPage'
import type { RunResponse, PipelineDetail } from '@/types'

/** 构造 run 响应 */
function makeRun(overrides: Partial<RunResponse> = {}): RunResponse {
  return {
    id: 'run-abc',
    pipeline_name: 'demo',
    pipeline_file: 'demo.yaml',
    definition_id: 'abc123def456',
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

/** 构造 pipeline 详情 */
function makePipeline(overrides: Partial<PipelineDetail> = {}): PipelineDetail {
  return {
    id: 'pipe-1',
    name: 'demo',
    file: 'demo.yaml',
    content: 'tasks: []',
    ...overrides,
  } as PipelineDetail
}

function Wrapper({ id }: { id: string }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter initialEntries={[`/runs/${id}`]}>
          <Routes>
            <Route path="/runs/:id" element={<RunDetailPage />} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </QueryClientProvider>
  )
}

describe('<RunDetailPage /> Issue #57 - 历史运行必须用快照', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRunStagePanelProps.mockClear()
    mockUseCancelRun.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    mockUseRunConsole.mockReturnValue({ data: null })
    mockUseRetryVersions.mockReturnValue({ data: undefined })
    mockUseResultPage.mockReturnValue({ data: undefined })
    mockUseArtifacts.mockReturnValue({ data: undefined, isLoading: false, error: null })
  })

  it('使用快照渲染 TaskTree，且不调用 usePipeline', async () => {
    const run = makeRun()
    const snapshot = makePipeline({ id: 'snapshot-v1' })
    mockUseRun.mockReturnValue({ data: run, isLoading: false })
    mockUsePipelineSnapshot.mockReturnValue({ data: snapshot, isLoading: false, error: null })

    render(<Wrapper id="run-abc" />)

    await waitFor(() => {
      expect(screen.getByTestId('task-tree')).toBeInTheDocument()
    })

    // 关键断言 1：TaskTree 收到的是 snapshot 的 pipeline
    expect(mockTaskTreeProps).toHaveBeenCalled()
    const lastProps = mockTaskTreeProps.mock.calls.at(-1)![0] as { pipeline: PipelineDetail }
    expect(lastProps.pipeline.id).toBe('snapshot-v1')

    // 关键断言 2：usePipeline 从未被调用（禁止回退到当前 pipeline 文件）
    expect(mockUsePipeline).not.toHaveBeenCalled()
  })

  it('快照加载中显示占位文案', async () => {
    mockUseRun.mockReturnValue({ data: makeRun(), isLoading: false })
    mockUsePipelineSnapshot.mockReturnValue({ data: undefined, isLoading: true, error: null })

    render(<Wrapper id="run-abc" />)

    await waitFor(() => {
      expect(screen.getByText(/加载历史快照中/i)).toBeInTheDocument()
    })
    // 此时不应渲染 TaskTree
    expect(screen.queryByTestId('task-tree')).not.toBeInTheDocument()
  })

  it('快照加载失败时显示错误占位', async () => {
    mockUseRun.mockReturnValue({ data: makeRun(), isLoading: false })
    mockUsePipelineSnapshot.mockReturnValue({ data: undefined, isLoading: false, error: new Error('boom') })

    render(<Wrapper id="run-abc" />)

    await waitFor(() => {
      expect(screen.getByText(/历史快照加载失败/i)).toBeInTheDocument()
    })
    // 即便出错，也不应回退到 usePipeline
    expect(mockUsePipeline).not.toHaveBeenCalled()
  })

  // v2 (2026-09): 头部重排 — 标题优先、操作右置，锁定信息层级与开关可访问性
  it('头部以运行名为标题、面包屑展示所属流水线，操作区位于标题之后', async () => {
    mockUseRun.mockReturnValue({ data: makeRun({ display_name: 'keen_bear', pipeline_name: 'test-pipeline' }), isLoading: false })
    mockUsePipelineSnapshot.mockReturnValue({ data: makePipeline(), isLoading: false, error: null })

    render(<Wrapper id="run-abc" />)

    const heading = await screen.findByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('keen_bear')
    expect(screen.getByText('test-pipeline')).toBeInTheDocument()

    // 操作按钮在标题之后（DOM 顺序），避免用户先看到操作再看到页面主体
    const refreshBtn = screen.getByRole('button', { name: /刷新/ })
    const position = heading.compareDocumentPosition(refreshBtn)
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('任务树收起入口位于树面板内，收起后在原位置提供展开入口', async () => {
    mockUseRun.mockReturnValue({ data: makeRun(), isLoading: false })
    mockUsePipelineSnapshot.mockReturnValue({ data: makePipeline(), isLoading: false, error: null })

    render(<Wrapper id="run-abc" />)

    await waitFor(() => {
      expect(screen.getByTestId('task-tree')).toBeInTheDocument()
    })
    // TaskTree 收到"收起"回调，按钮渲染在树面板内部（由 TaskTree 负责）
    expect(mockTaskTreeProps.mock.calls.at(-1)![0].onCollapse).toBeTypeOf('function')

    fireEvent.click(screen.getByTestId('tree-collapse'))

    // 收起后树卸载，原位置（左侧）保留展开按钮
    expect(screen.queryByTestId('task-tree')).not.toBeInTheDocument()
    const expandBtn = screen.getByRole('button', { name: '显示任务树' })
    fireEvent.click(expandBtn)
    expect(screen.getByTestId('task-tree')).toBeInTheDocument()
  })

  it('Debug 切换按钮文案稳定，aria-pressed 反映状态', async () => {
    mockUseRun.mockReturnValue({ data: makeRun(), isLoading: false })
    mockUsePipelineSnapshot.mockReturnValue({ data: makePipeline(), isLoading: false, error: null })

    render(<Wrapper id="run-abc" />)

    const btn = await screen.findByRole('button', { name: 'Debug' })
    expect(btn).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(btn)

    expect(screen.getByRole('button', { name: 'Debug' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('Issue #113 / v3: 进度徽标悬浮展示执行节点面板，并传入快照和任务运行记录', async () => {
    const run = makeRun({
      tasks: [
        {
          id: 'tr-1',
          run_id: 'run-abc',
          task_name: 'demo.build',
          subpipeline_name: 'demo',
          task_type: 'command',
          status: 'success',
          exit_code: 0,
          error: null,
          log_path: '',
          started_at: null,
          finished_at: null,
          created_at: '',
        },
      ],
    })
    const snapshot = makePipeline({
      id: 'snapshot-v1',
      pipelines: [
        {
          name: 'demo',
          depends_on: [],
          tasks: [{ name: 'build', command: 'make', env: {}, retry: 0, depends_on: [] }],
        },
      ],
    })
    mockUseRun.mockReturnValue({ data: run, isLoading: false })
    mockUsePipelineSnapshot.mockReturnValue({ data: snapshot, isLoading: false, error: null })

    render(<Wrapper id="run-abc" />)

    const badge = await screen.findByTestId('progress-badge')
    // 悬浮前不渲染节点面板，避免头部常驻占位
    expect(screen.queryByTestId('run-stage-panel')).not.toBeInTheDocument()

    fireEvent.mouseEnter(badge)

    await waitFor(() => {
      expect(screen.getByTestId('run-stage-panel')).toBeInTheDocument()
    })

    expect(mockRunStagePanelProps).toHaveBeenCalled()
    const lastProps = mockRunStagePanelProps.mock.calls.at(-1)![0] as { pipeline: PipelineDetail; taskRuns: unknown[] }
    expect(lastProps.pipeline.id).toBe('snapshot-v1')
    expect(lastProps.taskRuns).toHaveLength(1)
  })
})
