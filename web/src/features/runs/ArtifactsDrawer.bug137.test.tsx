import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp } from 'antd'

// ---- Mocks for api/runs ----
const mockUseArtifacts = vi.fn()

vi.mock('@/api/runs', async () => {
  const actual = await vi.importActual<typeof import('@/api/runs')>('@/api/runs')
  return { ...actual, useArtifacts: (id?: string) => mockUseArtifacts(id) }
})

// ---- Types ----
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
    task_name: 'task1',
    path: 'file.txt',
    size: 100,
    mtime: '2026-06-25T12:00:00Z',
    content_type: 'text/plain',
    ...overrides,
  }
}

function makeResponse(overrides: Partial<ArtifactListResponse> = {}): ArtifactListResponse {
  return { run_id: 'run-1', default: [], artifacts: [], ...overrides }
}

// ---- Wrapper ----
function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>{children}</AntdApp>
    </QueryClientProvider>
  )
}

import ArtifactsDrawer from './ArtifactsDrawer'

// ====================================================================
//  Bug #137: TypeScript TS2322 — ArtifactLeafNode 类型缺少 item 属性
//  buildTree() 返回类型声明为 ArtifactLeafNode[]，但返回的分组节点
//  (含 selectable:false 和 children) 缺少 item 属性，导致 tsc --noEmit 失败
// ====================================================================

describe('Bug #137 — buildTree 类型错误回归测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseArtifacts.mockReset()
  })

  it('单一 task 单个文件 — 树节点正确渲染', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({ artifacts: [makeArtifact({ task_name: 'task1', path: 'a.txt' })] }),
      isLoading: false,
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    await waitFor(() => {
      expect(screen.getByText('task1')).toBeInTheDocument()
      expect(screen.getByText('a.txt')).toBeInTheDocument()
    })
  })

  it('单一 task 多个文件 — 分组节点下所有子节点正确渲染', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        artifacts: [
          makeArtifact({ task_name: 'task1', path: 'a.txt' }),
          makeArtifact({ task_name: 'task1', path: 'b.txt' }),
          makeArtifact({ task_name: 'task1', path: 'c.txt' }),
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
      expect(screen.getByText('task1')).toBeInTheDocument()
      expect(screen.getByText('a.txt')).toBeInTheDocument()
      expect(screen.getByText('b.txt')).toBeInTheDocument()
      expect(screen.getByText('c.txt')).toBeInTheDocument()
    })
  })

  it('多个 task 各含文件 — 分组节点与子节点正确渲染', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        artifacts: [
          makeArtifact({ task_name: 'build', path: 'out.bin' }),
          makeArtifact({ task_name: 'build', path: 'build.log' }),
          makeArtifact({ task_name: 'test', path: 'report.xml' }),
          makeArtifact({ task_name: 'test', path: 'coverage.json' }),
          makeArtifact({ task_name: 'deploy', path: 'status.txt' }),
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
      expect(screen.getByText('build')).toBeInTheDocument()
      expect(screen.getByText('out.bin')).toBeInTheDocument()
      expect(screen.getByText('build.log')).toBeInTheDocument()
      expect(screen.getByText('test')).toBeInTheDocument()
      expect(screen.getByText('report.xml')).toBeInTheDocument()
      expect(screen.getByText('coverage.json')).toBeInTheDocument()
      expect(screen.getByText('deploy')).toBeInTheDocument()
      expect(screen.getByText('status.txt')).toBeInTheDocument()
    })
  })

  it('空 artifacts 列表 — 不渲染任何树节点', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({ artifacts: [] }),
      isLoading: false,
    })
    render(
      <Wrapper>
        <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
      </Wrapper>,
    )
    await waitFor(() => {
      expect(document.querySelector('.ant-empty')).toBeTruthy()
      expect(document.querySelector('.ant-tree')).toBeFalsy()
    })
  })

  it('artifacts 包含特殊字符的 task_name 和 path — 正常渲染', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        artifacts: [
          makeArtifact({ task_name: 'step-1_test', path: 'output (2).log' }),
          makeArtifact({ task_name: 'step-1_test', path: 'data/results.json' }),
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
      expect(screen.getByText('step-1_test')).toBeInTheDocument()
      expect(screen.getByText('output (2).log')).toBeInTheDocument()
      expect(screen.getByText('data/results.json')).toBeInTheDocument()
    })
  })
})
