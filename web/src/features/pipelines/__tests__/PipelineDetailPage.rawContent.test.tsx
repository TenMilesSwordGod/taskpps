import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'
import type { PipelineDetail } from '@/types'

/**
 * 回归测试（2026-09）：Web「YAML 编辑器」必须优先展示文件原文 raw_content。
 *
 * 背景：此前编辑器内容由 /by-id 返回的已解析模型 pipelineToYaml 重新序列化，
 * Pydantic schema 未声明的字段（如用户流水线里的裸 `task:` 步骤列表）被静默丢弃，
 * 用户看到的内容与真实文件不一致。
 *
 * 契约：存在 raw_content 时，点「YAML 编辑器」后 CodeMirror 收到的 value
 * 必须等于 raw_content；缺失时才回退 pipelineToYaml。
 */

const RAW_YAML = `name: raw-fidelity
pipelines:
  - name: test
    tasks:
      - name: hello
        command: echo "Hello from taskpps"
        retry: 0
      - name: steps-task
        task:
          - run: ls
        retry: 0
`

const mockPipeline: PipelineDetail = {
  name: 'raw-fidelity',
  raw_content: RAW_YAML,
  pipelines: [
    {
      name: 'test',
      depends_on: [],
      tasks: [
        { name: 'hello', command: 'echo "Hello from taskpps"', env: {}, retry: 0, depends_on: [] },
        // 模型侧 task 字段已被后端丢弃：编辑器不应依赖它
        { name: 'steps-task', env: {}, retry: 0, depends_on: [] },
      ],
    },
  ],
}

vi.mock('@/api/pipelines', () => ({
  usePipelineById: () => ({ data: mockPipeline, isLoading: false }),
  usePipelineByFile: () => ({ data: undefined, isLoading: false }),
  useSavePipelineById: () => ({ mutate: vi.fn(), isPending: false }),
  useSavePipelineByFile: () => ({ mutate: vi.fn(), isPending: false }),
}))

// 权限与项目配置接口：本用例只关心原文展示，避免真实网络请求
vi.mock('@/hooks/useIsAdmin', () => ({ useIsAdmin: () => false }))
vi.mock('@/api/agents', () => ({ useAgentsWithConfig: () => ({ data: [] }) }))
vi.mock('@/api/credentials', () => ({ useCredentials: () => ({ data: [] }) }))

// 画布组件依赖 ReactFlow 测量，jsdom 下 mock 为容器
vi.mock('@/features/pipelines/workflow/WorkflowEditor', async () => {
  const React = await import('react')
  const Mock = React.forwardRef(() => React.createElement('div', { 'data-testid': 'workflow-editor' }))
  return { default: Mock }
})
vi.mock('@/features/pipelines/NodePalette', () => ({ default: () => <div /> }))
vi.mock('@/features/pipelines/PropertyPanel', () => ({ default: () => <div /> }))
vi.mock('@/components/PipelineBreadcrumb', () => ({ default: () => <div /> }))
vi.mock('@/components/TriggerRunModal', () => ({ default: () => <div /> }))

// 捕获编辑器实际收到的 value（forwardRef：页面会传 ref，避免 React 警告）
vi.mock('@/features/pipelines/YamlEditor', async () => {
  const React = await import('react')
  const Mock = React.forwardRef(
    (props: { value: string }, _ref: React.Ref<unknown>) =>
      React.createElement('div', { 'data-testid': 'yaml-editor' }, props.value),
  )
  return { default: Mock }
})

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

describe('PipelineDetailPage — YAML 编辑器展示文件原文', () => {
  afterEach(() => cleanup())

  it('存在 raw_content 时编辑器展示原文（保留 task: 等模型未声明字段）', () => {
    render(
      <Wrapper>
        <PipelineDetailPage />
      </Wrapper>,
    )

    fireEvent.click(screen.getByText('YAML 编辑器'))

    const editor = screen.getByTestId('yaml-editor')
    expect(editor.textContent).toContain('task:')
    expect(editor.textContent).toContain('run: ls')
    expect(editor.textContent).toBe(RAW_YAML)
  })
})
