/**
 * PipelineDetailPage（查看模式 YAML）UX 补测（2026-09，QA 审计）。
 *
 * 覆盖维度：未保存状态可见性 / 离开守卫 / 保存反馈。
 * 背景：现有用例覆盖 raw_content 原文展示；但查看模式下修改 YAML 后
 * 无脏标记、无路由/关闭守卫、保存成功失败无断言，修改可能静默丢失。
 *
 * `it.fails` = 已确认缺陷（修复后改回 it，详见 .debug/qa-audit/report-web-ux-gaps.md）。
 * v2 (2026-09, issue #216): 未保存标记/离开守卫已实现，用例已转为常规断言。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { App as AntdApp, message } from 'antd'
import type { ReactNode } from 'react'
import type { PipelineDetail } from '@/types'

const RAW_YAML = `name: raw-fidelity
pipelines:
  - name: test
    tasks:
      - name: hello
        command: echo hello
`

const mockPipeline: PipelineDetail = {
  name: 'raw-fidelity',
  raw_content: RAW_YAML,
  pipelines: [
    {
      name: 'test',
      depends_on: [],
      tasks: [{ name: 'hello', command: 'echo hello', env: {}, retry: 0, depends_on: [] }],
    },
  ],
}

const mockMutateById = vi.fn()
const mockMutateByFile = vi.fn()

vi.mock('@/api/pipelines', () => ({
  usePipelineById: () => ({ data: mockPipeline, isLoading: false }),
  usePipelineByFile: () => ({ data: undefined, isLoading: false }),
  useSavePipelineById: () => ({ mutate: mockMutateById, isPending: false }),
  useSavePipelineByFile: () => ({ mutate: mockMutateByFile, isPending: false }),
}))

vi.mock('@/hooks/useIsAdmin', () => ({ useIsAdmin: () => false }))
vi.mock('@/api/agents', () => ({ useAgentsWithConfig: () => ({ data: [] }) }))
vi.mock('@/api/credentials', () => ({ useCredentials: () => ({ data: [] }) }))

vi.mock('@/features/pipelines/workflow/WorkflowEditor', async () => {
  const React = await import('react')
  const Mock = React.forwardRef(() => React.createElement('div', { 'data-testid': 'workflow-editor' }))
  return { default: Mock }
})
vi.mock('@/features/pipelines/NodePalette', () => ({ default: () => <div /> }))
vi.mock('@/features/pipelines/PropertyPanel', () => ({ default: () => <div /> }))
vi.mock('@/components/PipelineBreadcrumb', () => ({ default: () => <div /> }))
vi.mock('@/components/TriggerRunModal', () => ({ default: () => <div /> }))

// 编辑器桩：可输入（触发 onChange）、可保存（触发 onSave），用于验证页面层契约
vi.mock('@/features/pipelines/YamlEditor', async () => {
  const React = await import('react')
  const Mock = React.forwardRef(
    (props: { value: string; onChange: (t: string) => void; onSave?: () => void }) =>
      React.createElement(
        'div',
        null,
        // 必须用 textarea：YAML 含换行，input 会静默吞掉 \n 导致内容断言失真
        React.createElement('textarea', {
          'aria-label': 'yaml-input',
          value: props.value,
          onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => props.onChange(e.target.value),
        }),
        React.createElement('button', { type: 'button', onClick: () => props.onSave?.() }, 'mock-save'),
      ),
  )
  return { default: Mock }
})

const PipelineDetailPage = (await import('@/features/pipelines/PipelineDetailPage')).default

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter initialEntries={['/pipelines/proj-1/def-12345678']}>
          <Routes>
            <Route path="/pipelines/:projectId/:definitionId" element={children} />
          </Routes>
        </MemoryRouter>
      </AntdApp>
    </QueryClientProvider>
  )
}

/** 打开 YAML 编辑器并返回输入框 */
function openEditor() {
  render(
    <Wrapper>
      <PipelineDetailPage />
    </Wrapper>,
  )
  fireEvent.click(screen.getByText('YAML 编辑器'))
  return screen.getByLabelText('yaml-input') as HTMLInputElement
}

beforeEach(() => {
  mockMutateById.mockReset()
  mockMutateByFile.mockReset()
})

afterEach(() => cleanup())

describe('<PipelineDetailPage /> 查看模式 YAML UX-未保存状态', () => {
  it('UX-修改 YAML 后展示「未保存」标记，提示用户改动未落盘', () => {
    const input = openEditor()
    fireEvent.change(input, { target: { value: RAW_YAML + '\n# changed' } })

    expect(screen.getByText(/未保存/)).toBeInTheDocument()
  })

  it('UX-查看模式存在未保存修改时注册 beforeunload 守卫，防止关闭标签页丢失', () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const input = openEditor()
    fireEvent.change(input, { target: { value: RAW_YAML + '\n# changed' } })

    expect(addSpy.mock.calls.some((c) => c[0] === 'beforeunload')).toBe(true)
    addSpy.mockRestore()
  })
})

describe('<PipelineDetailPage /> 查看模式 YAML UX-保存反馈', () => {
  it('UX-保存触发接口且携带修改后的内容', () => {
    const input = openEditor()
    fireEvent.change(input, { target: { value: 'name: changed\npipelines: []\n' } })
    fireEvent.click(screen.getByText('mock-save'))

    expect(mockMutateById).toHaveBeenCalledWith('name: changed\npipelines: []\n', expect.any(Object))
  })

  it('UX-保存成功后提示「已保存」', () => {
    const successSpy = vi.spyOn(message, 'success')
    mockMutateById.mockImplementation((_content: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.())
    const input = openEditor()
    fireEvent.change(input, { target: { value: 'name: changed\npipelines: []\n' } })
    fireEvent.click(screen.getByText('mock-save'))

    expect(successSpy).toHaveBeenCalledWith('已保存')
    successSpy.mockRestore()
  })

  it('UX-保存失败时提示失败原因且编辑器内容保留（不丢用户输入）', () => {
    const errorSpy = vi.spyOn(message, 'error')
    mockMutateById.mockImplementation((_content: string, opts?: { onError?: (e: Error) => void }) => opts?.onError?.(new Error('409 冲突')))
    const input = openEditor()
    fireEvent.change(input, { target: { value: 'name: changed\npipelines: []\n' } })
    fireEvent.click(screen.getByText('mock-save'))

    expect(errorSpy).toHaveBeenCalledWith('保存失败: 409 冲突')
    expect((screen.getByLabelText('yaml-input') as HTMLInputElement).value).toBe('name: changed\npipelines: []\n')
    errorSpy.mockRestore()
  })
})
