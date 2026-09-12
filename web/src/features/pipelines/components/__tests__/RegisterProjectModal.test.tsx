import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App as AntdApp } from 'antd'
import RegisterProjectModal from '../RegisterProjectModal'

const mockRegisterProject = vi.fn()
vi.mock('@/api/projects', () => ({
  useRegisterProject: () => ({ mutateAsync: mockRegisterProject, isPending: false }),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AntdApp>{children}</AntdApp>
}

describe('<RegisterProjectModal /> v3', () => {
  beforeEach(() => {
    mockRegisterProject.mockReset()
  })

  it('提交 workdir 与可选名称，成功后关闭', async () => {
    mockRegisterProject.mockResolvedValue({ id: 'p1', name: 'App', workdir: '/srv/app' })
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<RegisterProjectModal open onClose={onClose} />, { wrapper: Wrapper })

    await user.type(screen.getByPlaceholderText('/path/to/your/project'), '/srv/app')
    await user.type(screen.getByPlaceholderText('留空则显示为目录名'), 'App')
    await user.click(screen.getByRole('button', { name: /注\s*册/ }))

    await waitFor(() => expect(mockRegisterProject).toHaveBeenCalledTimes(1))
    expect(mockRegisterProject).toHaveBeenCalledWith({ workdir: '/srv/app', name: 'App' })
    expect(onClose).toHaveBeenCalled()
  })

  it('workdir 为空时阻止提交', async () => {
    const user = userEvent.setup()
    render(<RegisterProjectModal open onClose={vi.fn()} />, { wrapper: Wrapper })

    await user.click(screen.getByRole('button', { name: /注\s*册/ }))
    expect(mockRegisterProject).not.toHaveBeenCalled()
  })
})
