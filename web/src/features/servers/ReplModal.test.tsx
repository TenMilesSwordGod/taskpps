import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import ReplModal from './ReplModal';
import type { AgentWithConfig } from '@/types';

// ReplModal 测试：mock 网络层（execStream / complete），验证 Tab 补全与输入提示交互

vi.mock('./execStream', () => ({
  execCommandStream: vi.fn(),
}));

const fetchCompletionsMock = vi.fn();
vi.mock('./complete', () => ({
  fetchCompletions: (...args: unknown[]) => fetchCompletionsMock(...args),
}));

import { execCommandStream } from './execStream';

function makeAgent(overrides: Partial<AgentWithConfig> = {}): AgentWithConfig {
  return {
    agent_id: 'agent-1',
    name: 'Test Agent',
    type: 'ssh-linux',
    host: '10.0.0.1',
    port: 22,
    source_file: 'test.yaml',
    connected: true,
    project_id: '',
    project_name: '',
    hostname: 'test-host',
    platform: 'linux',
    system: 'Ubuntu 22.04',
    arch: 'x86_64',
    ip: '10.0.0.1',
    agent_version: '1.0.0',
    agent_pid: 1234,
    connected_at: 1700000000,
    last_heartbeat: 1700000000,
    running_commands: 0,
    queued_commands: 0,
    max_parallel: 1,
    net_status: 'reachable',
    last_execution_time: 0,
    ...overrides,
  };
}

function renderRepl() {
  const utils = render(<ReplModal open agent={makeAgent()} onClose={() => {}} />);
  return { ...utils, getInput: () => screen.getByPlaceholderText('输入命令…') as HTMLInputElement };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

beforeEach(() => {
  fetchCompletionsMock.mockReset();
  (execCommandStream as ReturnType<typeof vi.fn>).mockReset();
});

describe('ReplModal 输入提示（tip）', () => {
  it('输入后防抖弹出候选列表，Esc 关闭', async () => {
    fetchCompletionsMock.mockResolvedValue({ prefix: 'py', candidates: ['python3', 'python2'] });
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'py' } });
    input.setSelectionRange(2, 2);

    // 防抖 150ms 后应展示候选列表
    await waitFor(() => expect(screen.getByText('python3')).toBeInTheDocument());
    expect(screen.getByText('python2')).toBeInTheDocument();
    // 请求应带上当前输入与光标位置
    expect(fetchCompletionsMock).toHaveBeenCalledWith('agent-1', 'py', 2, '', expect.any(AbortSignal));

    fireEvent.keyDown(input, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByText('python3')).not.toBeInTheDocument());
  });

  it('光标不在末尾时不触发提示', async () => {
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'py x' } });
    input.setSelectionRange(2, 2); // 光标在中间

    await new Promise((r) => setTimeout(r, 300));
    expect(fetchCompletionsMock).not.toHaveBeenCalled();
  });

  it('返回 null（失败/离线）时不渲染列表', async () => {
    fetchCompletionsMock.mockResolvedValue(null);
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'py' } });
    input.setSelectionRange(2, 2);

    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByText(/python/)).not.toBeInTheDocument();
  });

  it('输入变化后旧请求结果被丢弃（竞态）', async () => {
    const first = deferred<{ prefix: string; candidates: string[] }>();
    fetchCompletionsMock.mockReturnValueOnce(first.promise);
    fetchCompletionsMock.mockResolvedValue({ prefix: 'python', candidates: ['python3'] });
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'py' } });
    input.setSelectionRange(2, 2);
    await waitFor(() => expect(fetchCompletionsMock).toHaveBeenCalledTimes(1));

    // 第一个请求未返回时用户继续输入，触发新请求
    fireEvent.change(input, { target: { value: 'python' } });
    input.setSelectionRange(6, 6);
    await waitFor(() => expect(fetchCompletionsMock).toHaveBeenCalledTimes(2));

    // 旧请求结果返回：与当前输入 "python" 不匹配，应被丢弃
    await act(async () => { first.resolve({ prefix: 'py', candidates: ['pyspark'] }); });
    expect(screen.queryByText('pyspark')).not.toBeInTheDocument();

    // 新请求结果返回：匹配当前输入，单候选直接上屏（设计：不弹列表）
    await waitFor(() => expect(input.value).toBe('python3'));
  });
});

describe('ReplModal Tab 补全', () => {
  it('唯一候选时 Tab 直接补全且不弹列表', async () => {
    fetchCompletionsMock.mockResolvedValue({ prefix: 'py', candidates: ['python3'] });
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'py' } });
    input.setSelectionRange(2, 2);

    fireEvent.keyDown(input, { key: 'Tab' });

    await waitFor(() => expect(input.value).toBe('python3'));
    expect(screen.queryByText('python3')).not.toBeInTheDocument();
  });

  it('多候选时 Tab 打开列表，再次 Tab 循环，Enter 上屏且不执行', async () => {
    fetchCompletionsMock.mockResolvedValue({ prefix: 'ls', candidates: ['ls', 'lsblk'] });
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'ls' } });
    input.setSelectionRange(2, 2);

    fireEvent.keyDown(input, { key: 'Tab' });
    await waitFor(() => expect(screen.getByText('lsblk')).toBeInTheDocument());

    // Tab 循环到第二个候选，Enter 上屏
    fireEvent.keyDown(input, { key: 'Tab' });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(input.value).toBe('lsblk'));
    // Enter 上屏候选不应触发命令执行
    expect(execCommandStream).not.toHaveBeenCalled();
  });

  it('方向键选择候选后 Enter 上屏', async () => {
    fetchCompletionsMock.mockResolvedValue({ prefix: '/', candidates: ['/home/', '/opt/'] });
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'cd /' } });
    input.setSelectionRange(4, 4);

    fireEvent.keyDown(input, { key: 'Tab' });
    await waitFor(() => expect(screen.getByText('/opt/')).toBeInTheDocument());

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(input.value).toBe('cd /opt/'));
    expect(execCommandStream).not.toHaveBeenCalled();
  });

  it('列表打开时 ArrowUp/Down 不应触发历史翻页', async () => {
    fetchCompletionsMock.mockResolvedValue({ prefix: 'ls', candidates: ['ls', 'lsblk'] });
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'ls' } });
    input.setSelectionRange(2, 2);
    fireEvent.keyDown(input, { key: 'Tab' });
    await waitFor(() => expect(screen.getByText('lsblk')).toBeInTheDocument());

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(input.value).toBe('lsblk'));

    // 选中项被上屏后列表关闭，此时 ArrowUp 恢复历史行为（当前无历史，不应变化）
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(input.value).toBe('lsblk');
  });

  it('切换 session 后关闭候选列表', async () => {
    fetchCompletionsMock.mockResolvedValue({ prefix: 'py', candidates: ['python3', 'python2'] });
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'py' } });
    input.setSelectionRange(2, 2);
    await waitFor(() => expect(screen.getByText('python3')).toBeInTheDocument());

    // 点击"添加 Session"切换活动会话
    fireEvent.click(screen.getByText('添加 Session'));
    await waitFor(() => expect(screen.queryByText('python3')).not.toBeInTheDocument());
  });

  it('提交执行后候选列表关闭', async () => {
    fetchCompletionsMock.mockResolvedValue({ prefix: 'py', candidates: ['python3', 'python2'] });
    (execCommandStream as ReturnType<typeof vi.fn>).mockImplementation(() => Promise.resolve());
    const { getInput } = renderRepl();
    const input = getInput();

    fireEvent.change(input, { target: { value: 'py' } });
    input.setSelectionRange(2, 2);
    await waitFor(() => expect(screen.getByText('python3')).toBeInTheDocument());

    // 直接回车执行（列表存在但用户直接回车 = 执行当前输入）
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(execCommandStream).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText('python3')).not.toBeInTheDocument());
  });
});
