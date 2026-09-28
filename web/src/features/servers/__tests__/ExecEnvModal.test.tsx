import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App as AntdApp } from 'antd'
import ExecEnvModal from '../ExecEnvModal'
import type { AgentWithConfig } from '@/types'

const mockUpdate = vi.fn()

vi.mock('@/api/agents', () => ({
  useUpdateAgent: () => ({ mutateAsync: mockUpdate, isPending: false }),
}))

function makeAgent(overrides: Partial<AgentWithConfig> = {}): AgentWithConfig {
  return {
    agent_id: 'env-1',
    name: '环境机',
    type: 'ssh-username-password',
    host: '10.0.0.1',
    port: 22,
    source_file: 'agents/env-1.yaml',
    connected: true,
    project_id: 'p1',
    project_name: '项目甲',
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
    max_parallel: 1,
    net_status: 'unknown',
    last_execution_time: 0,
    shell: '/bin/bash',
    env: { JAVA_HOME: '/opt/jdk', LANG: 'en_US.UTF-8' },
    ...overrides,
  }
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return <AntdApp>{children}</AntdApp>
}

describe('<ExecEnvModal />', () => {
  beforeEach(() => {
    mockUpdate.mockReset()
  })

  it('编辑态：回填 shell/env，保存时提交 payload 到 YAML', async () => {
    mockUpdate.mockResolvedValue({})
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<ExecEnvModal open agent={makeAgent()} canEdit onClose={onClose} />, { wrapper: Wrapper })

    const shellInput = screen.getByPlaceholderText('/bin/bash（留空使用默认）')
    expect(shellInput).toHaveValue('/bin/bash')
    // EnvEditor 现有行回填
    expect(screen.getByDisplayValue('JAVA_HOME')).toBeInTheDocument()

    await user.clear(shellInput)
    await user.type(shellInput, '/bin/zsh')
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1))
    expect(mockUpdate).toHaveBeenCalledWith({
      projectId: 'p1',
      agentId: 'env-1',
      payload: { shell: '/bin/zsh', env: { JAVA_HOME: '/opt/jdk', LANG: 'en_US.UTF-8' } },
    })
    expect(onClose).toHaveBeenCalled()
  })

  it('编辑态：清空 shell 与环境变量表示恢复默认（提交空值清除）', async () => {
    mockUpdate.mockResolvedValue({})
    const user = userEvent.setup()
    render(<ExecEnvModal open agent={makeAgent()} canEdit onClose={vi.fn()} />, { wrapper: Wrapper })

    await user.clear(screen.getByPlaceholderText('/bin/bash（留空使用默认）'))
    // 删除两行环境变量（AntD 图标按钮的 aria-label 为 delete）；每删一行后重新查询
    await user.click(screen.getAllByRole('button', { name: 'delete' })[0])
    await user.click(screen.getAllByRole('button', { name: 'delete' })[0])
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1))
    expect(mockUpdate.mock.calls[0][0].payload).toEqual({ shell: '', env: {} })
  })

  it('编辑态：非法环境变量名阻止保存并提示', async () => {
    const user = userEvent.setup()
    render(
      <ExecEnvModal open agent={makeAgent({ env: {} })} canEdit onClose={vi.fn()} />,
      { wrapper: Wrapper },
    )

    await user.type(screen.getByPlaceholderText('KEY'), '1BAD-KEY')
    await user.type(screen.getByPlaceholderText('VALUE'), 'x')
    await user.click(screen.getByRole('button', { name: /保\s*存/ }))

    // 内联错误常驻 + 点击保存时的 toast 均会命中，这里只要求提示出现且未提交
    await waitFor(() => expect(screen.getAllByText(/环境变量名非法/).length).toBeGreaterThan(0))
    expect(mockUpdate).not.toHaveBeenCalled()
  })

  it('打开期间 agent 引用更新（列表轮询）不覆盖未保存编辑', async () => {
    const user = userEvent.setup()
    const { rerender } = render(
      <ExecEnvModal open agent={makeAgent()} canEdit onClose={vi.fn()} />,
      { wrapper: Wrapper },
    )

    const shellInput = screen.getByPlaceholderText('/bin/bash（留空使用默认）')
    await user.clear(shellInput)
    await user.type(shellInput, '/bin/fish')

    // 5s 轮询会返回新的 agent 对象（引用变化但编辑应保留）
    rerender(<ExecEnvModal open agent={makeAgent({ shell: '/bin/bash' })} canEdit onClose={vi.fn()} />)
    expect(shellInput).toHaveValue('/bin/fish')
  })

  it('关闭后重新打开按最新 agent 值回填', () => {
    const { rerender } = render(
      <ExecEnvModal open agent={makeAgent()} canEdit onClose={vi.fn()} />,
      { wrapper: Wrapper },
    )
    expect(screen.getByPlaceholderText('/bin/bash（留空使用默认）')).toHaveValue('/bin/bash')

    rerender(<ExecEnvModal open={false} agent={makeAgent()} canEdit onClose={vi.fn()} />)
    rerender(<ExecEnvModal open agent={makeAgent({ shell: '/bin/zsh' })} canEdit onClose={vi.fn()} />)
    expect(screen.getByPlaceholderText('/bin/bash（留空使用默认）')).toHaveValue('/bin/zsh')
  })

  it('默认项目（无 project_id）保存时给出明确提示且不提交', async () => {
    const user = userEvent.setup()
    render(
      <ExecEnvModal open agent={makeAgent({ project_id: '' })} canEdit onClose={vi.fn()} />,
      { wrapper: Wrapper },
    )

    await user.click(screen.getByRole('button', { name: /保\s*存/ }))
    await waitFor(() => expect(screen.getAllByText(/已注册项目/).length).toBeGreaterThan(0))
    expect(mockUpdate).not.toHaveBeenCalled()
  })

  it('只读态：展示 shell/env 但不显示保存按钮', () => {
    render(<ExecEnvModal open agent={makeAgent()} canEdit={false} onClose={vi.fn()} />, { wrapper: Wrapper })

    expect(screen.getByText('/bin/bash')).toBeInTheDocument()
    expect(screen.getByText('JAVA_HOME')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /保\s*存/ })).not.toBeInTheDocument()
  })

  it('未配置时展示默认提示', () => {
    render(
      <ExecEnvModal open agent={makeAgent({ shell: '', env: {} })} canEdit={false} onClose={vi.fn()} />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText(/默认/)).toBeInTheDocument()
    expect(screen.getByText(/未配置环境变量/)).toBeInTheDocument()
  })
})
