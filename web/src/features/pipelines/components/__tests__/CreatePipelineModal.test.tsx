import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App as AntdApp } from 'antd'
import CreatePipelineModal from '../CreatePipelineModal'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

const mockUseProjects = vi.fn()
vi.mock('@/api/projects', () => ({
  useProjects: () => mockUseProjects(),
}))

const mockUsePipelines = vi.fn()
const mockCreatePipeline = vi.fn()
vi.mock('@/api/pipelines', () => ({
  usePipelines: () => mockUsePipelines(),
  useCreatePipeline: () => ({ mutateAsync: mockCreatePipeline, isPending: false }),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AntdApp>{children}</AntdApp>
}

describe('<CreatePipelineModal /> v3', () => {
  beforeEach(() => {
    mockNavigate.mockReset()
    mockUseProjects.mockReset()
    mockUsePipelines.mockReset()
    mockCreatePipeline.mockReset()
    mockUseProjects.mockReturnValue({ data: [{ id: 'p1', name: 'Proj1', workdir: '/x' }] })
    mockUsePipelines.mockReturnValue({ data: { items: [], folders: [] } })
  })

  it('单一项目默认选中：创建空白模板并跳转编辑页', async () => {
    mockCreatePipeline.mockResolvedValue({ status: 'ok', file: 'demo.yaml', definition_id: 'def-1' })
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<CreatePipelineModal open onClose={onClose} />, { wrapper: Wrapper })

    await user.type(screen.getByPlaceholderText(/deploy\.yaml/), 'demo')
    await user.click(screen.getByRole('button', { name: '创建并编辑' }))

    await waitFor(() => expect(mockCreatePipeline).toHaveBeenCalledTimes(1))
    const arg = mockCreatePipeline.mock.calls[0][0]
    expect(arg.projectId).toBe('p1')
    expect(arg.file).toBe('demo.yaml')
    expect(arg.content).toContain('name: demo')
    expect(arg.content).toContain('tasks: []')
    expect(onClose).toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith('/pipelines/p1/def-1')
  })

  it('文件夹 + 示例模板：生成嵌套路径与 shell 示例内容', async () => {
    mockCreatePipeline.mockResolvedValue({ status: 'ok', file: 'debug/deploy.yaml', definition_id: 'def-2' })
    const user = userEvent.setup()
    render(<CreatePipelineModal open onClose={vi.fn()} />, { wrapper: Wrapper })

    // AutoComplete 的 placeholder 渲染为 span 而非 input 属性，按 combobox 顺序取文件夹输入框
    const combos = screen.getAllByRole('combobox')
    await user.type(combos[1], 'debug/')
    await user.type(screen.getByPlaceholderText(/deploy\.yaml/), 'deploy')
    await user.click(screen.getByText('示例（shell 任务）'))
    await user.click(screen.getByRole('button', { name: '创建并编辑' }))

    await waitFor(() => expect(mockCreatePipeline).toHaveBeenCalledTimes(1))
    const arg = mockCreatePipeline.mock.calls[0][0]
    expect(arg.file).toBe('debug/deploy.yaml')
    expect(arg.content).toContain('echo "Hello from taskpps"')
  })

  it('无项目时禁用创建并提示先注册项目', () => {
    mockUseProjects.mockReturnValue({ data: [] })
    render(<CreatePipelineModal open onClose={vi.fn()} />, { wrapper: Wrapper })

    expect(screen.getByText('暂无可选项目，请先注册项目目录')).toBeInTheDocument()
  })
})
