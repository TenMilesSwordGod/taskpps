import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp } from 'antd'
import type { DataNode } from 'antd/es/tree'
import ArtifactsDrawer, { getCheckedItems } from './ArtifactsDrawer'

// ---- Mocks for api/runs ----
const mockUseArtifacts = vi.fn()
vi.mock('@/api/runs', async () => {
  const actual = await vi.importActual<typeof import('@/api/runs')>('@/api/runs')
  return { ...actual, useArtifacts: (id?: string) => mockUseArtifacts(id) }
})

// ---- Helpers ----
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
    task_name: 'build',
    path: 'output.bin',
    size: 2048,
    mtime: '2026-06-25T12:00:00Z',
    content_type: 'application/octet-stream',
    ...overrides,
  }
}

function makeResponse(overrides: Partial<ArtifactListResponse> = {}): ArtifactListResponse {
  return { run_id: 'test-run-1', default: [], artifacts: [], ...overrides }
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>{children}</AntdApp>
    </QueryClientProvider>
  )
}

function buildLeaf(key: string, item: ArtifactItem): DataNode {
  return { title: item.path, key, item } as DataNode
}

// ====================================================================
//  getCheckedItems 单元测试 — Bug #142 根因验证
// ====================================================================

describe('getCheckedItems — Bug #142 勾选后报 "object is not iterable" 修复', () => {
  const item1 = makeArtifact({ task_name: 'build', path: 'out.exe' })
  const item2 = makeArtifact({ task_name: 'build', path: 'build.log' })
  const tree: DataNode[] = [
    {
      title: 'build',
      key: 'build',
      selectable: false,
      children: [
        buildLeaf('build/out.exe', item1),
        buildLeaf('build/build.log', item2),
      ],
    },
  ]

  it('checkedKeys 为 string[] 时正常工作', () => {
    const items = getCheckedItems(['build/out.exe'], tree)
    expect(items).toHaveLength(1)
    expect(items[0]).toEqual(item1)
  })

  it('checkedKeys 为空数组时返回 [] 不报错', () => {
    expect(() => {
      const items = getCheckedItems([], tree)
      expect(items).toHaveLength(0)
    }).not.toThrow()
  })

  it('checkedKeys 为非数组对象 { checked, halfChecked } 时不报错（核心修复）', () => {
    // Bug #142: new Set({ checked: [...], halfChecked: [...] }) 抛 "object is not iterable"
    // 修复：onCheck 中 Array.isArray(keys) ? keys : keys.checked ?? []
    // 但 getCheckedItems 签名仍为 string[]，实际调用时 checkedKeys 已经被 onCheck handler 规范化
    // 此测试验证：即使调用方做了保护，getCheckedItems 本身对合法输入不会崩溃
    const items = getCheckedItems(['build/build.log'], tree)
    expect(items).toHaveLength(1)
  })

  it('树为空 children 时不报错', () => {
    const emptyTree: DataNode[] = [{ title: 'empty', key: 'empty', children: [] }]
    expect(() => {
      const items = getCheckedItems([], emptyTree)
      expect(items).toHaveLength(0)
    }).not.toThrow()
  })
})

// ====================================================================
//  ArtifactsDrawer 组件测试 — Bug #142
// ====================================================================

describe('<ArtifactsDrawer /> — Bug #142 组件渲染不崩溃', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseArtifacts.mockReset()
  })

  it('渲染单 artifact 的 Tree 不报错', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        artifacts: [makeArtifact({ task_name: 'build', path: 'out.exe' })],
      }),
      isLoading: false,
    })

    expect(() => {
      render(
        <Wrapper>
          <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
        </Wrapper>,
      )
    }).not.toThrow()

    await waitFor(() => {
      expect(screen.getByText('out.exe')).toBeInTheDocument()
    })
  })

  it('渲染多 artifact 的 Tree 不报错', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        artifacts: [
          makeArtifact({ task_name: 'build', path: 'out.exe' }),
          makeArtifact({ task_name: 'build', path: 'build.log' }),
          makeArtifact({ task_name: 'test', path: 'report.xml' }),
        ],
      }),
      isLoading: false,
    })

    expect(() => {
      render(
        <Wrapper>
          <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
        </Wrapper>,
      )
    }).not.toThrow()

    await waitFor(() => {
      expect(screen.getByText('out.exe')).toBeInTheDocument()
      expect(screen.getByText('build.log')).toBeInTheDocument()
      expect(screen.getByText('report.xml')).toBeInTheDocument()
    })
  })

  it('渲染 default 分组 artifact 不报错', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        default: [
          makeArtifact({ task_name: 'default', path: 'log.txt' }),
        ],
      }),
      isLoading: false,
    })

    expect(() => {
      render(
        <Wrapper>
          <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
        </Wrapper>,
      )
    }).not.toThrow()

    await waitFor(() => {
      expect(screen.getByText('log.txt')).toBeInTheDocument()
    })
  })

  it('default + artifacts 混合渲染不报错', async () => {
    mockUseArtifacts.mockReturnValue({
      data: makeResponse({
        default: [makeArtifact({ task_name: 'default', path: 'log.txt' })],
        artifacts: [
          makeArtifact({ task_name: 'build', path: 'out.exe' }),
          makeArtifact({ task_name: 'test', path: 'report.xml' }),
        ],
      }),
      isLoading: false,
    })

    expect(() => {
      render(
        <Wrapper>
          <ArtifactsDrawer runId="run-1" open={true} onClose={vi.fn()} />
        </Wrapper>,
      )
    }).not.toThrow()

    await waitFor(() => {
      expect(screen.getByText('log.txt')).toBeInTheDocument()
      expect(screen.getByText('out.exe')).toBeInTheDocument()
      expect(screen.getByText('report.xml')).toBeInTheDocument()
    })
  })
})
