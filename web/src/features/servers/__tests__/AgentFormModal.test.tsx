import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App as AntdApp } from 'antd'
import AgentFormModal from '../AgentFormModal'
import type { AgentWithConfig, ProjectResponse } from '@/types'

const mockCreate = vi.fn()
const mockUpdate = vi.fn()
const mockTry = vi.fn()

vi.mock('@/api/agents', () => ({
  useCreateAgent: () => ({ mutateAsync: mockCreate, isPending: false }),
  useUpdateAgent: () => ({ mutateAsync: mockUpdate, isPending: false }),
  useTryConnectAgent: () => ({ mutateAsync: mockTry, isPending: false }),
}))

vi.mock('@/api/credentials', () => ({
  useCredentials: () => ({
    data: [{ id: 'cred-1', name: '生产 SSH', username: 'deploy', has_password: true, type: 'ssh-username-password' }],
  }),
  useCreateCredential: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateCredential: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

const projects: ProjectResponse[] = [
  { id: 'p1', name: '项目甲', workdir: '/srv/p1', registered_at: '', last_used_at: null, active: true },
]

const editAgent: AgentWithConfig = {
  agent_id: 'old-01',
  name: '旧名字',
  description: '原描述',
  type: 'ssh-username-password',
  host: '10.0.0.1',
  port: 22,
  source_file: 'agents/old-01.yaml',
  connected: false,
  project_id: 'p1',
  project_name: '项目甲',
  username: 'deploy',
  credential_id: 'cred-1',
  execution_agent: false,
  agent_auto_bootstrap: true,
  hostname: '',
  platform: '',
  system: '',
  arch: '',
  ip: '',
  agent_version: '',
  agent_pid: 0,
  connected_at: 0,
  last_heartbeat: 0,
  running_commands: 0,
  queued_commands: 0,
  max_parallel: 2,
  net_status: 'unknown',
  last_execution_time: 0,
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AntdApp>{children}</AntdApp>
}

describe('<AgentFormModal />', () => {
  beforeEach(() => {
    mockCreate.mockReset()
    mockUpdate.mockReset()
    mockTry.mockReset()
  })

  it('新增：提交项目/ID/host 等表单字段并关闭', async () => {
    mockCreate.mockResolvedValue({ agent_id: 'web-9' })
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <AgentFormModal open agent={null} projects={projects} defaultProjectId="p1" onClose={onClose} />,
      { wrapper: Wrapper },
    )

    await user.type(screen.getByPlaceholderText('web-01'), 'web-9')
    await user.type(screen.getByPlaceholderText('10.0.0.1'), '10.1.1.1')
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1))
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        project_id: 'p1',
        id: 'web-9',
        host: '10.1.1.1',
        port: 22,
        execution_agent: true,
      }),
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('新增：非法 ID 阻止提交并提示规则', async () => {
    const user = userEvent.setup()
    render(
      <AgentFormModal open agent={null} projects={projects} defaultProjectId="p1" onClose={vi.fn()} />,
      { wrapper: Wrapper },
    )

    await user.type(screen.getByPlaceholderText('web-01'), '..bad')
    await user.type(screen.getByPlaceholderText('10.0.0.1'), '10.1.1.1')
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() =>
      expect(screen.getByText(/只能包含字母、数字、下划线、点和短横线/)).toBeInTheDocument(),
    )
    expect(mockCreate).not.toHaveBeenCalled()
  })

  it('新增：ID 创建后不可编辑，编辑态回填且 ID 输入禁用', async () => {
    render(<AgentFormModal open agent={editAgent} projects={projects} onClose={vi.fn()} />, { wrapper: Wrapper })

    expect(screen.getByDisplayValue('old-01')).toBeDisabled()
    expect(screen.getByDisplayValue('旧名字')).toBeInTheDocument()
    expect(screen.getByDisplayValue('10.0.0.1')).toBeInTheDocument()
  })

  it('编辑：只提交可改字段（不含 project_id/id）', async () => {
    mockUpdate.mockResolvedValue({})
    const user = userEvent.setup()
    render(<AgentFormModal open agent={editAgent} projects={projects} onClose={vi.fn()} />, { wrapper: Wrapper })

    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1))
    const call = mockUpdate.mock.calls[0][0]
    expect(call.projectId).toBe('p1')
    expect(call.agentId).toBe('old-01')
    expect(call.payload).not.toHaveProperty('project_id')
    expect(call.payload).not.toHaveProperty('id')
    expect(call.payload.execution_agent).toBe(false)
  })

  it('编辑：测试连接成功给出结果反馈', async () => {
    mockTry.mockResolvedValue({ status: 'connected', latency_ms: 12, error: null })
    const user = userEvent.setup()
    render(<AgentFormModal open agent={editAgent} projects={projects} onClose={vi.fn()} />, { wrapper: Wrapper })

    await user.click(screen.getByRole('button', { name: /测试连接/ }))
    await waitFor(() => expect(mockTry).toHaveBeenCalledWith('old-01'))
  })

  it('新增：测试连接按钮禁用（需先保存）', () => {
    render(
      <AgentFormModal open agent={null} projects={projects} defaultProjectId="p1" onClose={vi.fn()} />,
      { wrapper: Wrapper },
    )
    expect(screen.getByRole('button', { name: /测试连接/ })).toBeDisabled()
  })
})
