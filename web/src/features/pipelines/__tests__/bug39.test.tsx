import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'
import type { PipelineDetail } from '@/types'
import { parseYamlToPipeline } from '@/utils/yamlParser'

/**
 * Bug #39 RED 测试：[web] PDP 编辑模式保存输出的 YAML name=unnamed
 * （editNodes 未被初始填充）
 *
 * 数据流（见 .debug/bugfix-206-context.md）：
 *   PipelineDetailPage 维护 editNodes/editEdges（useState 初始 []）。
 *   进入编辑模式渲染 WorkflowEditor（内部用 yamlToNodes(pipeline) 解析节点）。
 *   保存时调用 nodesToYaml(editNodes, editEdges) → pipelineName =
 *     (pipelineNode?.data?.label) || 'unnamed'（nodesToYaml.ts:48-49）。
 *
 * 根因疑似：进入 editMode 时 PipelineDetailPage 未用 yamlToNodes(pipeline)
 * 初始化 editNodes/editEdges，且 WorkflowEditor 的 onGraphChange 仅在保存/连线
 * 时触发、初始不触发。于是 editNodes 始终为空 → 保存得到 name: unnamed。
 *
 * 本 RED 测试契约：进入编辑模式后点「保存」，保存回调收到的 YAML 反序列化后
 * 的 pipeline.name 必须等于真实流水线名（非 'unnamed'），且包含 SubPipeline/Task。
 * 修复前 editNodes=[] → name='unnamed' → 断言失败（确定性 RED）。
 */

// ---------- 构造最小真实 pipeline（非 hardcode 兜底，是复刻合法数据结构）----------
const REAL_NAME = 'my-real-pipeline'
const mockPipeline: PipelineDetail = {
  name: REAL_NAME,
  pipelines: [
    {
      name: 'build',
      depends_on: [],
      tasks: [
        {
          name: 'compile',
          command: 'make',
          env: {},
          retry: 0,
          depends_on: [],
        },
      ],
    },
  ],
}

// ---------- 捕获保存内容的 mock ----------
const capturedContent: { value: string | null } = { value: null }
const mockSaveByIdMutate = vi.fn((content: string) => {
  capturedContent.value = content
})

vi.mock('@/api/pipelines', () => ({
  usePipelineById: () => ({ data: mockPipeline, isLoading: false }),
  usePipelineByFile: () => ({ data: undefined, isLoading: false }),
  useSavePipelineById: () => ({ mutate: mockSaveByIdMutate, isPending: false }),
  useSavePipelineByFile: () => ({ mutate: vi.fn(), isPending: false }),
}))

// 编辑模式才渲染的重组件：mock 为简单容器，避免 ReactFlow/jsdom 测量问题。
// 关键：bug 在于 PipelineDetailPage 自身未初始化 editNodes，与 WorkflowEditor
// 内部渲染无关，因此 mock 后只依赖页面层初始化逻辑（即疑似修复点）。
vi.mock('@/features/pipelines/workflow/WorkflowEditor', () => ({
  default: (props: { pipeline?: PipelineDetail }) => (
    <div data-testid="workflow-editor">{props.pipeline?.name}</div>
  ),
  WorkflowEditorRef: null,
}))

vi.mock('@/features/pipelines/NodePalette', () => ({
  default: () => <div data-testid="node-palette" />,
}))

vi.mock('@/features/pipelines/PropertyPanel', () => ({
  default: () => <div data-testid="property-panel" />,
}))

// 初始（查看模式）渲染的组件，避免重渲染/portal 干扰
vi.mock('@/features/pipelines/PipelineGraph', () => ({
  default: () => <div data-testid="pipeline-graph" />,
}))
vi.mock('@/features/pipelines/YamlEditor', () => ({
  default: () => <div data-testid="yaml-editor" />,
}))
vi.mock('@/components/PipelineBreadcrumb', () => ({
  default: () => <div data-testid="breadcrumb" />,
}))
vi.mock('@/components/TriggerRunModal', () => ({
  default: () => <div data-testid="trigger-run" />,
}))
vi.mock('@/components/HelpPanel', () => ({
  HelpPanel: () => <div data-testid="help-panel" />,
}))

// 页面模块必须在所有 vi.mock 之后导入
const PipelineDetailPage = (await import('@/features/pipelines/PipelineDetailPage')).default

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter initialEntries={['/pipelines/proj-1/def-123']}>
          <Routes>
            <Route path="/pipelines/:projectId/:definitionId" element={children} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </QueryClientProvider>
  )
}

describe('Bug#39 — PDP 编辑模式保存 YAML name 应为真实流水线名（非 unnamed）', () => {
  beforeEach(() => {
    capturedContent.value = null
    mockSaveByIdMutate.mockClear()
  })
  afterEach(() => cleanup())

  it('RED: 进入编辑模式并保存，输出 YAML 的 name 应等于真实流水线名', async () => {
    render(
      <Wrapper>
        <PipelineDetailPage />
      </Wrapper>,
    )

    // 1) 进入编辑模式
    const editBtn = screen.getByText('编辑模式')
    fireEvent.click(editBtn)

    // 2) 点击「保存」
    const saveBtn = await screen.findByText('保存')
    fireEvent.click(saveBtn)

    // 3) 断言保存内容（修复前 editNodes=[] → name='unnamed'，此断言失败）
    expect(capturedContent.value).not.toBeNull()
    const parsed = parseYamlToPipeline(capturedContent.value!)
    expect(parsed.success).toBe(true)
    expect(parsed.pipeline?.name).toBe(REAL_NAME)
    expect(parsed.pipeline?.name).not.toBe('unnamed')
  })

  it('RED: 保存输出应含 SubPipeline(build) 与 Task(compile)，而非空', async () => {
    render(
      <Wrapper>
        <PipelineDetailPage />
      </Wrapper>,
    )

    fireEvent.click(screen.getByText('编辑模式'))
    const saveBtn = await screen.findByText('保存')
    fireEvent.click(saveBtn)

    expect(capturedContent.value).not.toBeNull()
    const parsed = parseYamlToPipeline(capturedContent.value!)
    expect(parsed.success).toBe(true)
    const subs = parsed.pipeline?.pipelines ?? []
    expect(subs.length).toBe(1)
    expect(subs[0].name).toBe('build')
    expect(subs[0].tasks[0].name).toBe('compile')
  })
})
