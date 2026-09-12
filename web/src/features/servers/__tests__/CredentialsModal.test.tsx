import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App as AntdApp } from 'antd'
import CredentialsModal from '../CredentialsModal'
import type { CredentialView } from '@/types'

const mockUseCredentials = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/api/credentials', () => ({
  useCredentials: (...args: unknown[]) => mockUseCredentials(...args),
  useDeleteCredential: () => ({ mutateAsync: mockDelete, isPending: false }),
  useCreateCredential: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateCredential: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('@/api/projects', () => ({
  useProjects: () => ({
    data: [
      { id: 'p1', name: '项目甲', workdir: '/srv/p1', registered_at: '', last_used_at: null, active: true },
    ],
    isLoading: false,
  }),
}))

const credential: CredentialView = {
  id: 'prod-ssh',
  name: '生产 SSH',
  description: '',
  type: 'ssh-username-password',
  username: 'deploy',
  key_path: '',
  has_password: true,
  has_passphrase: false,
  source_file: 'credentials/prod-ssh.yaml',
  project_id: 'p1',
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AntdApp>{children}</AntdApp>
}

describe('<CredentialsModal />', () => {
  beforeEach(() => {
    mockUseCredentials.mockReset()
    mockDelete.mockReset()
    mockUseCredentials.mockReturnValue({ data: [credential], isLoading: false, isError: false, error: null })
  })

  it('展示凭据元数据且不出现密码明文', () => {
    render(<CredentialsModal open initialProjectId="p1" onClose={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.getByText('prod-ssh')).toBeInTheDocument()
    expect(screen.getByText('生产 SSH')).toBeInTheDocument()
    expect(screen.getByText('密码已保存')).toBeInTheDocument()
    expect(screen.queryByText(/password/i)).not.toBeInTheDocument()
  })

  it('空列表时给出下一步引导', () => {
    mockUseCredentials.mockReturnValue({ data: [], isLoading: false, isError: false, error: null })
    render(<CredentialsModal open initialProjectId="p1" onClose={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.getByText(/暂无凭据/)).toBeInTheDocument()
  })

  it('删除凭据需二次确认后调用接口', async () => {
    mockDelete.mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(<CredentialsModal open initialProjectId="p1" onClose={vi.fn()} />, { wrapper: Wrapper })

    // 行内删除按钮 → Popconfirm 二次确认；确认按钮文本就是「删 除」
    await user.click(screen.getByRole('button', { name: '删除凭据 prod-ssh' }))
    await user.click(await screen.findByRole('button', { name: /^删\s*除$/ }))
    await waitFor(() =>
      expect(mockDelete).toHaveBeenCalledWith({ projectId: 'p1', credentialId: 'prod-ssh' }),
    )
  })

  it('点击新增凭据打开表单弹窗', async () => {
    const user = userEvent.setup()
    render(<CredentialsModal open initialProjectId="p1" onClose={vi.fn()} />, { wrapper: Wrapper })
    await user.click(screen.getByRole('button', { name: /新增凭据/ }))
    await waitFor(() => expect(screen.getByPlaceholderText('prod-ssh')).toBeInTheDocument())
  })
})
