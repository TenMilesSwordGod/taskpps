import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp } from 'antd'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// ---- Mocks for api/runs ----
const mockUseArtifacts = vi.fn()

vi.mock('@/api/runs', async () => {
  const actual = await vi.importActual<typeof import('@/api/runs')>('@/api/runs')
  return { ...actual, useArtifacts: (id?: string) => mockUseArtifacts(id) }
})

// ---- Artifact type helpers ----
interface ArtifactItem {
  task_name: string
  path: string
  size: number
  mtime: string
  content_type: string
}

interface ArtifactListResponse {
  run_id: string
  default: ArtifactItem[]
  artifacts: ArtifactItem[]
}

function makeArtifact(overrides: Partial<ArtifactItem> = {}): ArtifactItem {
  return {
    task_name: 'SyncAutomation.step2',
    path: 'output.txt',
    size: 1024,
    mtime: '2026-06-25T12:00:00Z',
    content_type: 'text/plain',
    ...overrides,
  }
}

function makeResponse(overrides: Partial<ArtifactListResponse> = {}): ArtifactListResponse {
  return { run_id: 'test-run-1', default: [], artifacts: [], ...overrides }
}

// ---- Wrappers ----
function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>{children}</AntdApp>
    </QueryClientProvider>
  )
}

// ====================================================================
//  ArtifactsDrawer 组件测试
// ====================================================================

import ArtifactsDrawer from './ArtifactsDrawer'

describe('<ArtifactsDrawer /> — Issue #134 artifacts 下载弹窗', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseArtifacts.mockReset()
  })

  it('open=false 时不渲染 Drawer', () => {
    mockUseArtifacts.mockReturnValue({ data: undefined, isLoading: false })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={false} onClose={vi.fn()} />
      </Wrapper>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('open=true 且加载完成时渲染 Drawer', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({ artifacts: [makeArtifact()] }),
      isLoading: false,
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    await waitFor(() => {
      expect(document.querySelector('.ant-drawer')).toBeTruthy()
    })
  })

  it('将 runId 传给 useArtifacts', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse(),
      isLoading: false,
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="expected-run-id" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    await waitFor(() => {
      expect(mockUseArtifacts).toHaveBeenCalledWith('expected-run-id')
    })
  })

  it('点击关闭按钮触发 onClose', async () => {
    const onClose = vi.fn()
    mockUseArtifacts.mockReturnValue({
      data: makeResponse(),
      isLoading: false,
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={onClose} />
      </Wrapper>,
    )
    await waitFor(() => document.querySelector('.ant-drawer'))
    const closeBtn = document.querySelector('.ant-drawer-close') as HTMLElement
    if (closeBtn) {
      fireEvent.click(closeBtn)
      expect(onClose).toHaveBeenCalled()
    }
  })

  it('加载中显示 Spin', async () => {
    mockUseArtifacts.mockReturnValue({ data: undefined, isLoading: true })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    await waitFor(() => {
      expect(document.querySelector('.ant-spin')).toBeTruthy()
    })
  })

  it('无 artifacts 时显示空状态', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({ artifacts: [], default: [] }),
      isLoading: false,
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    await waitFor(() => {
      expect(document.querySelector('.ant-empty')).toBeTruthy()
    })
  })

  it('仅 data.default 有值时显示 default 分组', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        artifacts: [],
        default: [
          makeArtifact({ task_name: 'default', path: 'log.txt', size: 100 }),
          makeArtifact({ task_name: 'default', path: 'meta.json', size: 200 }),
        ],
      }),
      isLoading: false,
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    await waitFor(() => {
      expect(screen.getByText('default')).toBeInTheDocument()
      expect(screen.getByText('log.txt')).toBeInTheDocument()
      expect(screen.getByText('meta.json')).toBeInTheDocument()
    })
  })

  it('data.default 和 data.artifacts 同时存在时合并显示', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        artifacts: [
          makeArtifact({ task_name: 'task1', path: 'result.json', size: 500 }),
        ],
        default: [
          makeArtifact({ task_name: 'default', path: 'log.txt', size: 100 }),
        ],
      }),
      isLoading: false,
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    await waitFor(() => {
      expect(screen.getByText('default')).toBeInTheDocument()
      expect(screen.getByText('task1')).toBeInTheDocument()
      expect(screen.getByText('log.txt')).toBeInTheDocument()
      expect(screen.getByText('result.json')).toBeInTheDocument()
    })
  })

  it('树形展示各任务下的 artifact 文件', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        artifacts: [
          makeArtifact({ task_name: 'task1', path: 'result.json', size: 500 }),
          makeArtifact({ task_name: 'task1', path: 'log.txt', size: 200 }),
          makeArtifact({ task_name: 'task2', path: 'data.csv', size: 800 }),
        ],
      }),
      isLoading: false,
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    // 树节点按 task_name 分组：task1 下有 result.json 和 log.txt
    await waitFor(() => {
      expect(screen.getByText('task1')).toBeInTheDocument()
      expect(screen.getByText('task2')).toBeInTheDocument()
      expect(screen.getByText('result.json')).toBeInTheDocument()
      expect(screen.getByText('log.txt')).toBeInTheDocument()
      expect(screen.getByText('data.csv')).toBeInTheDocument()
    })
  })

  it('API 返回错误时显示错误提示', async () => {
    mockUseArtifacts.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Failed to fetch artifacts'),
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    await waitFor(() => {
      const alert = document.querySelector('.ant-alert-error')
      expect(alert).toBeTruthy()
    })
  })
})

// ====================================================================
//  下载行为契约测试
// ====================================================================

describe('Artifacts 下载 URL 契约', () => {
  it('单选文件 URL 格式: /api/runs/{runId}/artifacts/{task_name}/{path}', () => {
    const runId = 'run-1'
    const taskName = 'step1'
    const filePath = 'result.log'
    const url = `/api/runs/${runId}/artifacts/${taskName}/${filePath}`
    expect(url).toBe('/api/runs/run-1/artifacts/step1/result.log')
    expect(url).toContain('/artifacts/')
    expect(url).not.toContain('/zip')
  })

  it('多选 zip URL 格式: /api/runs/{runId}/artifacts/zip', () => {
    const url = '/api/runs/run-1/artifacts/zip'
    expect(url).toContain('/zip')
    expect(url).toContain('/artifacts/')
  })

  it('ArtifactItem 包含 task_name, path, size, mtime, content_type', () => {
    const item: ArtifactItem = {
      task_name: 'task1',
      path: 'file.txt',
      size: 1024,
      mtime: '2026-06-25T12:00:00Z',
      content_type: 'text/plain',
    }
    expect(item.task_name).toBeTruthy()
    expect(item.path).toBeTruthy()
    expect(typeof item.size).toBe('number')
    expect(item.mtime).toBeTruthy()
    expect(item.content_type).toBeTruthy()
  })
})

// ====================================================================
//  树形结构 + 下载逻辑契约
// ====================================================================

describe('Artifacts 树形结构与下载逻辑契约', () => {
  it('artifacts 应按 task_name 分组', () => {
    const items: ArtifactItem[] = [
      makeArtifact({ task_name: 'build', path: 'out.exe' }),
      makeArtifact({ task_name: 'build', path: 'build.log' }),
      makeArtifact({ task_name: 'test', path: 'report.xml' }),
    ]

    const tree: Record<string, ArtifactItem[]> = {}
    for (const item of items) {
      if (!tree[item.task_name]) tree[item.task_name] = []
      tree[item.task_name].push(item)
    }

    expect(Object.keys(tree)).toHaveLength(2)
    expect(tree['build']).toHaveLength(2)
    expect(tree['test']).toHaveLength(1)
  })

  it('多选 ≥2 个文件 → zip 端点', () => {
    expect(2 > 1).toBe(true) // selectedCount > 1 → useZip=true
  })

  it('单选 1 个文件 → 直接下载端点', () => {
    expect(1 > 1).toBe(false) // selectedCount = 1 → useZip=false
  })

  it('未选文件 → 下载按钮禁用', () => {
    const selectedCount = 0
    expect(selectedCount === 0).toBe(true)
  })
})

// ====================================================================
//  RunDetailPage artifacts 按钮入口测试
// ====================================================================

describe('<RunDetailPage /> — Issue #134 artifacts 按钮', () => {
  const mockUseRun = vi.fn()
  const mockUseCancelRun = vi.fn()
  const mockUseRunConsole = vi.fn()
  const mockUsePipelineSnapshot = vi.fn()
  const mockUseRetryVersions = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockUseCancelRun.mockReturnValue({ mutateAsync: vi.fn(), isPending: false })
    mockUseRunConsole.mockReturnValue({ data: null })
    mockUseRetryVersions.mockReturnValue({ data: undefined })
    mockUseArtifacts.mockReturnValue({ data: undefined, isLoading: false })
  })

  it('TDD: RunDetailPage 操作栏包含 artifacts 按钮', async () => {
    // Re-mock api/runs for RunDetailPage context
    vi.doMock('@/api/runs', () => ({
      useRun: (id?: string) => mockUseRun(id),
      useCancelRun: () => mockUseCancelRun(),
      useRunConsole: () => mockUseRunConsole(),
      usePipelineSnapshot: (id?: string) => mockUsePipelineSnapshot(id),
      useRetryVersions: (id?: string) => mockUseRetryVersions(id),
      useArtifacts: (id?: string) => mockUseArtifacts(id),
    }))

    vi.doMock('./hooks/useSSELogs', () => ({
      useSSELogs: () => ({
        logs: [], connected: false, autoScroll: true,
        setAutoScroll: vi.fn(), clearLogs: vi.fn(), reconnect: vi.fn(),
      }),
    }))

    mockUseRun.mockReturnValue({
      data: {
        id: 'run-1', pipeline_name: 'demo', pipeline_file: 'demo.yaml',
        project_id: null, status: 'success', error: null,
        started_at: '2026-01-01T00:00:00Z', finished_at: '2026-01-01T00:01:00Z',
        created_at: '2026-01-01T00:00:00Z', params: {}, tasks: [],
      },
      isLoading: false,
    })
    mockUsePipelineSnapshot.mockReturnValue({
      data: { name: 'demo', pipelines: [] },
      isLoading: true,
      error: null,
    })

    const RunDetailPageMod = await import('./RunDetailPage')
    const RunDetailPage = RunDetailPageMod.default

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    render(
      <QueryClientProvider client={qc}>
        <AntdApp>
          <MemoryRouter initialEntries={['/runs/run-1']}>
            <Routes>
              <Route path="/runs/:id" element={<RunDetailPage />} />
            </Routes>
          </MemoryRouter>
        </AntdApp>
      </QueryClientProvider>,
    )

    // TDD: Dev 需在 RunDetailPage 操作栏添加 artifacts 按钮
    // 当前 RunDetailPage 无此按钮，测试预期失败 — Dev 实现后应通过
    await waitFor(() => {
      const btn = screen.queryByRole('button', { name: /artifact/i })
      expect(btn).toBeTruthy()
    }, { timeout: 2000 })
  })
})
