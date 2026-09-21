import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'
import type { PipelineDetail } from '@/types'

/**
 * v6 (2026-08): critique P1 — YAML 通道存在静默数据丢失路径
 *
 * 根因：handleToggleEditor 每次打开都用 pipelineToYaml(pipeline) 覆盖 yamlText，
 * 「打字→没保存→关闭→重开」草稿静默蒸发；且关闭无任何确认——与编辑模式
 * （有确认+beforeunload）双标。
 *
 * 契约：
 *   1. dirty 状态下关闭 → 弹确认，确认后才丢弃
 *   2. 重开 → 恢复草稿而非重新生成（草稿优先）
 *   3. 未修改时关闭 → 直接关闭无弹窗
 *   4. 保存成功 → dirty 清零，此后关闭不再弹窗
 */

const REAL_NAME = 'draft-guard-pipeline'
const mockPipeline: PipelineDetail = {
  name: REAL_NAME,
  pipelines: [
    {
      name: 'build',
      depends_on: [],
      tasks: [
        { name: 'compile', command: 'make', env: {}, retry: 0, depends_on: [] },
      ],
    },
  ],
}

// 保存 mutation mock：记录调用并同步触发 onSuccess（模拟服务端成功）
vi.mock('@/api/pipelines', () => ({
  usePipelineById: () => ({ data: mockPipeline, isLoading: false }),
  usePipelineByFile: () => ({ data: undefined, isLoading: false }),
  useSavePipelineById: () => ({
    mutate: (content: string, opts?: { onSuccess?: () => void }) =>
      opts?.onSuccess?.(),
    isPending: false,
  }),
  useSavePipelineByFile: () => ({ mutate: vi.fn(), isPending: false }),
}))

// YamlEditor mock：暴露 value / 触发 onChange / 触发 onSave 的最小面
const yamlMockState: {
  value: string
  onChange: ((v: string) => void) | null
  onSave: (() => void) | null
} = { value: '', onChange: null, onSave: null }
vi.mock('@/features/pipelines/YamlEditor', () => ({
  default: function YamlEditorMock(props: {
    value: string
    onChange: (v: string) => void
    onSave?: () => void
  }) {
    yamlMockState.value = props.value
    yamlMockState.onChange = props.onChange
    yamlMockState.onSave = props.onSave ?? null
    return (
      <div data-testid="yaml-editor">
        <span data-testid="yaml-value">{props.value}</span>
        <button
          data-testid="yaml-simulate-edit"
          onClick={() => props.onChange(`${props.value}\n# user-edited`)}
        >
          simulate-edit
        </button>
        {props.onSave && (
          // v7 (2026-08): onSave 签名改为可选内容参数，避免把 click 事件当内容传入
          <button data-testid="yaml-simulate-save" onClick={() => props.onSave?.()}>
            simulate-save
          </button>
        )}
      </div>
    )
  },
}))

vi.mock('@/features/pipelines/PipelineGraph', () => ({
  default: () => <div data-testid="pipeline-graph" />,
}))
vi.mock('@/features/pipelines/workflow/WorkflowEditor', () => ({
  default: () => <div data-testid="workflow-editor" />,
  WorkflowEditorRef: null,
}))
vi.mock('@/features/pipelines/workflow/NodePalette', () => ({ default: () => null }))
vi.mock('@/features/pipelines/workflow/PropertyPanel', () => ({ default: () => null }))
vi.mock('@/components/PipelineBreadcrumb', () => ({ default: () => <div /> }))
vi.mock('@/components/TriggerRunModal', () => ({ default: () => <div /> }))
vi.mock('@/components/HelpPanel', () => ({ HelpPanel: () => <div /> }))

const PipelineDetailPage = (await import('@/features/pipelines/PipelineDetailPage')).default

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter initialEntries={['/pipelines/proj-1/def-draft']}>
          <Routes>
            <Route path="/pipelines/:projectId/:definitionId" element={children} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </QueryClientProvider>
  )
}

async function openYamlEditor() {
  fireEvent.click(screen.getByRole('button', { name: /YAML 编辑器/ }))
  await waitFor(() => expect(screen.getByTestId('yaml-editor')).toBeInTheDocument())
}

async function closeViaToolbar() {
  fireEvent.click(screen.getByRole('button', { name: /关闭编辑器/ }))
}

describe('YAML 草稿保护（critique P1）', () => {
  beforeEach(() => {
    yamlMockState.onChange = null
    yamlMockState.onSave = null
    yamlMockState.value = ''
  })
  afterEach(() => {
    cleanup();
    // antd Modal.confirm 渲染在 document.body 的 portal 不随 RTL cleanup 移除，
    // 残留会导致下一用例 getByText 命中多个元素
    document.querySelectorAll('.ant-modal-root, .ant-modal-mask, .ant-modal-wrap').forEach((el) => el.remove());
  })

  it('RED: 取消关闭则草稿保留；确认放弃则重开为干净已存版本', async () => {
    render(
      <Wrapper>
        <PipelineDetailPage />
      </Wrapper>,
    )
    await openYamlEditor()
    const original = screen.getByTestId('yaml-value').textContent ?? ''
    expect(original).toContain(REAL_NAME)

    // 用户编辑 → dirty
    fireEvent.click(screen.getByTestId('yaml-simulate-edit'))

    // 关闭 → 必须出现确认对话框而不是静默关闭
    await closeViaToolbar()
    await waitFor(() =>
      expect(screen.getByText(/关闭编辑器将丢失未保存的内容/)).toBeInTheDocument(),
    )

    // 选择「继续编辑」（取消）→ 编辑器保持打开且草稿仍在
    fireEvent.click(screen.getByRole('button', { name: /继续编辑/ }))
    await waitFor(() =>
      expect(document.querySelector('.ant-modal-confirm')).toBeNull(),
    )
    expect(screen.getByTestId('yaml-value').textContent).toBe(`${original}\n# user-edited`)

    // 再次关闭 → 这次点「放弃并关闭」→ 显式丢弃
    await closeViaToolbar()
    await waitFor(() =>
      expect(screen.getByText(/关闭编辑器将丢失未保存的内容/)).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: /放弃并关闭/ }))
    await waitFor(() => expect(screen.queryByTestId('yaml-editor')).not.toBeInTheDocument())

    // 重开 → 应为干净的已保存版本（不含用户编辑痕迹）
    await openYamlEditor()
    expect(screen.getByTestId('yaml-value').textContent).toBe(original)
  })

  it('RED: 未修改时关闭直接关闭，不弹确认', async () => {
    render(
      <Wrapper>
        <PipelineDetailPage />
      </Wrapper>,
    )
    await openYamlEditor()
    await closeViaToolbar()
    await waitFor(() => expect(screen.queryByTestId('yaml-editor')).not.toBeInTheDocument())
    expect(screen.queryByText(/关闭编辑器将丢失未保存的内容/)).not.toBeInTheDocument()
  })

  it('RED: 保存成功后 dirty 清零，再次关闭不再弹确认且草稿与已存内容一致', async () => {
    render(
      <Wrapper>
        <PipelineDetailPage />
      </Wrapper>,
    )
    await openYamlEditor()

    // 编辑置 dirty → 保存（onSuccess 同步触发）→ dirty 应清零
    fireEvent.click(screen.getByTestId('yaml-simulate-edit'))
    fireEvent.click(screen.getByTestId('yaml-simulate-save'))
    const savedDraft = yamlMockState.value

    await closeViaToolbar()
    await waitFor(() => expect(screen.queryByTestId('yaml-editor')).not.toBeInTheDocument())
    // 已保存过：关闭不应再弹「放弃未保存」
    expect(screen.queryByText(/关闭编辑器将丢失未保存的内容/)).not.toBeInTheDocument()

    // 重开仍显示已保存内容（草稿=已保存内容）
    await openYamlEditor()
    expect(screen.getByTestId('yaml-value').textContent).toBe(savedDraft)
  })
})
