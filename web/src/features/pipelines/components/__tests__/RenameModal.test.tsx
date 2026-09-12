import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App as AntdApp } from 'antd'
import RenameModal from '../RenameModal'

const mockRenamePipeline = vi.fn()
const mockRenameFolder = vi.fn()
vi.mock('@/api/pipelines', () => ({
  useRenamePipeline: () => ({ mutateAsync: mockRenamePipeline, isPending: false }),
  useRenameFolder: () => ({ mutateAsync: mockRenameFolder, isPending: false }),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AntdApp>{children}</AntdApp>
}

describe('<RenameModal /> v3', () => {
  beforeEach(() => {
    mockRenamePipeline.mockReset()
    mockRenameFolder.mockReset()
    mockRenamePipeline.mockResolvedValue({ status: 'ok' })
    mockRenameFolder.mockResolvedValue({ status: 'ok' })
  })

  it('流水线重命名：省略后缀自动补 .yaml，并传给接口', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <RenameModal open onClose={onClose} kind="pipeline" projectId="p1" current="debug/demo.yaml" />,
      { wrapper: Wrapper },
    )

    const input = screen.getByDisplayValue('debug/demo.yaml')
    await user.clear(input)
    await user.type(input, 'prod/deploy')
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => expect(mockRenamePipeline).toHaveBeenCalledTimes(1))
    expect(mockRenamePipeline).toHaveBeenCalledWith({
      projectId: 'p1',
      file: 'debug/demo.yaml',
      newFile: 'prod/deploy.yaml',
    })
    expect(onClose).toHaveBeenCalled()
  })

  it('文件夹重命名：调用文件夹接口', async () => {
    const user = userEvent.setup()
    render(
      <RenameModal open onClose={vi.fn()} kind="folder" projectId="p1" current="debug" />,
      { wrapper: Wrapper },
    )

    const input = screen.getByDisplayValue('debug')
    await user.clear(input)
    await user.type(input, 'prod')
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => expect(mockRenameFolder).toHaveBeenCalledTimes(1))
    expect(mockRenameFolder).toHaveBeenCalledWith({
      projectId: 'p1',
      folder: 'debug',
      newFolder: 'prod',
    })
  })

  it('包含 .. 的路径被校验拦截', async () => {
    const user = userEvent.setup()
    render(
      <RenameModal open onClose={vi.fn()} kind="folder" projectId="p1" current="debug" />,
      { wrapper: Wrapper },
    )

    const input = screen.getByDisplayValue('debug')
    await user.clear(input)
    await user.type(input, '../escape')
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => expect(screen.getByText('路径不能包含 ..')).toBeInTheDocument())
    expect(mockRenameFolder).not.toHaveBeenCalled()
  })
})
