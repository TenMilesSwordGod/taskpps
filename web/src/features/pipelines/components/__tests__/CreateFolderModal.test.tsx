import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App as AntdApp } from 'antd'
import CreateFolderModal from '../CreateFolderModal'

const mockUseProjects = vi.fn()
vi.mock('@/api/projects', () => ({
  useProjects: () => mockUseProjects(),
}))

const mockUsePipelines = vi.fn()
const mockCreateFolder = vi.fn()
vi.mock('@/api/pipelines', () => ({
  usePipelines: () => mockUsePipelines(),
  useCreateFolder: () => ({ mutateAsync: mockCreateFolder, isPending: false }),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AntdApp>{children}</AntdApp>
}

describe('<CreateFolderModal /> v3', () => {
  beforeEach(() => {
    mockUseProjects.mockReset()
    mockUsePipelines.mockReset()
    mockCreateFolder.mockReset()
    mockUseProjects.mockReturnValue({ data: [{ id: 'p1', name: 'Proj1', workdir: '/x' }] })
    mockUsePipelines.mockReturnValue({ data: { items: [], folders: [] } })
  })

  it('创建多级文件夹：去掉首尾斜杠后调用接口', async () => {
    mockCreateFolder.mockResolvedValue({ status: 'ok', folder: 'debug/prod' })
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<CreateFolderModal open onClose={onClose} />, { wrapper: Wrapper })

    // AutoComplete 的 placeholder 渲染为 span 而非 input 属性，按 combobox 顺序取文件夹输入框
    const combos = screen.getAllByRole('combobox')
    await user.type(combos[1], '/debug/prod/')
    await user.click(screen.getByRole('button', { name: /创\s*建/ }))

    await waitFor(() => expect(mockCreateFolder).toHaveBeenCalledTimes(1))
    expect(mockCreateFolder).toHaveBeenCalledWith({ projectId: 'p1', folder: 'debug/prod' })
    expect(onClose).toHaveBeenCalled()
  })

  it('文件夹为空时阻止提交', async () => {
    const user = userEvent.setup()
    render(<CreateFolderModal open onClose={vi.fn()} />, { wrapper: Wrapper })

    await user.click(screen.getByRole('button', { name: /创\s*建/ }))
    expect(mockCreateFolder).not.toHaveBeenCalled()
  })
})
