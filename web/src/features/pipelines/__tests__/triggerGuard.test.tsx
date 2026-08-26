import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { forwardRef, useImperativeHandle } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'
import type { PipelineDetail } from '@/types'

/**
 * v6 (2026-08): critique P2 — 高风险时机错位。
 *
 * 编辑模式存在未保存修改（isDirty）时「触发运行」仍可直接执行，
 * 跑的是服务器上已保存的旧版本，无任何提示——用户以为跑的是刚改的流程。
 *
 * 契约：
 *   1. 非 dirty：点击直接打开运行弹窗
 *   2. dirty：先弹确认「画布有未保存的修改」；点「仍要运行」才打开弹窗
 */

const mockPipeline: PipelineDetail = {
  name: 'trigger-guard',
  pipelines: [
    { name: 'build', depends_on: [], tasks: [{ name: 't1', command: 'echo', env: {}, retry: 0, depends_on: [] }] },
  ],
}

vi.mock('@/api/pipelines', () => ({
  usePipelineById: () => ({ data: mockPipeline, isLoading: false }),
  usePipelineByFile: () => ({ data: undefined, isLoading: false }),
  useSavePipelineById: () => ({ mutate: vi.fn(), isPending: false }),
  useSavePipelineByFile: () => ({ mutate: vi.fn(), isPending: false }),
}))

// 编辑模式 dirty 开关（测试内切换）
const editorDirtyState = { value: false }

vi.mock('@/features/pipelines/workflow/WorkflowEditor', () => ({
  default: forwardRef((_props: Record<string, unknown>, ref) => {
    useImperativeHandle(ref, () => ({
      deleteNode: () => {},
      get isDirty() {
        return editorDirtyState.value
      },
    }))
    return <div data-testid="workflow-editor" />
  }),
  WorkflowEditorRef: null,
}))
vi.mock('@/features/pipelines/workflow/NodePalette', () => ({ default: () => null }))
vi.mock('@/features/pipelines/workflow/PropertyPanel', () => ({ default: () => null }))

// TriggerRunModal mock：记录 open prop
const triggerModalState = { openCount: 0 }
vi.mock('@/components/TriggerRunModal', () => ({
  default: (props: { open: boolean }) => {
    if (props.open && triggerModalState.openCount === 0) triggerModalState.openCount += 1
    else if (props.open) triggerModalState.openCount += 1
    return props.open ? <div data-testid="trigger-run-modal" /> : null
  },
}))
vi.mock('@/features/pipelines/PipelineGraph', () => ({ default: () => <div data-testid="pipeline-graph" /> }))
vi.mock('@/features/pipelines/YamlEditor', () => ({ default: () => <div data-testid="yaml-editor" /> }))
vi.mock('@/components/PipelineBreadcrumb', () => ({ default: () => <div /> }))
vi.mock('@/components/HelpPanel', () => ({ HelpPanel: () => <div /> }))

const PipelineDetailPage = (await import('@/features/pipelines/PipelineDetailPage')).default

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter initialEntries={['/pipelines/proj-1/def-trig']}>
          <Routes>
            <Route path="/pipelines/:projectId/:definitionId" element={children} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </QueryClientProvider>
  )
}

async function enterEditModeAndClickTrigger() {
  fireEvent.click(screen.getByRole('button', { name: /编辑模式/ }))
  await waitFor(() => expect(screen.getByTestId('workflow-editor')).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: /触发运行/ }))
}

describe('触发运行 — 脏状态守卫（critique P2）', () => {
  beforeEach(() => {
    editorDirtyState.value = false
    triggerModalState.openCount = 0
  })
  afterEach(() => {
    cleanup()
    document.querySelectorAll('.ant-modal-root, .ant-modal-mask, .ant-modal-wrap').forEach((el) => el.remove())
  })

  it('RED: 非 dirty 时点击触发运行，直接打开运行弹窗', async () => {
    render(
      <Wrapper>
        <PipelineDetailPage />
      </Wrapper>,
    )
    await enterEditModeAndClickTrigger()
    await waitFor(() => expect(screen.getByTestId('trigger-run-modal')).toBeInTheDocument())
    // 不应出现确认对话框
    expect(screen.queryByText(/未保存的修改.*将使用/)).not.toBeInTheDocument()
  })

  it('RED: dirty 时点击触发运行先弹确认；点「仍要运行」后才打开弹窗', async () => {
    editorDirtyState.value = true
    render(
      <Wrapper>
        <PipelineDetailPage />
      </Wrapper>,
    )
    await enterEditModeAndClickTrigger()

    // 确认对话框出现，且运行弹窗尚未打开
    await waitFor(() =>
      expect(screen.getByText(/本次运行将使用服务器上最近保存的版本/)).toBeInTheDocument(),
    )
    expect(screen.queryByTestId('trigger-run-modal')).not.toBeInTheDocument()

    // 明确选择仍要运行 → 打开运行弹窗
    fireEvent.click(screen.getByRole('button', { name: /仍要运行/ }))
    await waitFor(() => expect(screen.getByTestId('trigger-run-modal')).toBeInTheDocument())
  })

  it('RED: dirty 确认框中取消则不打开运行弹窗', async () => {
    editorDirtyState.value = true
    render(
      <Wrapper>
        <PipelineDetailPage />
      </Wrapper>,
    )
    await enterEditModeAndClickTrigger()
    await waitFor(() =>
      expect(screen.getByText(/本次运行将使用服务器上最近保存的版本/)).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: /返回保存/ }))
    await waitFor(() =>
      expect(document.querySelector('.ant-modal-confirm')).toBeNull(),
    )
    expect(screen.queryByTestId('trigger-run-modal')).not.toBeInTheDocument()
  })
})
