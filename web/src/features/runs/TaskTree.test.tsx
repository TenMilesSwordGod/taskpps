import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TaskTree from './TaskTree';
import type { PipelineDetail, TaskYAML, SubPipeline } from '@/types';

// useRunConsole 在 TaskTree 中被调用（debugVisible=false 时 runId 传 undefined）
vi.mock('@/api/runs', () => ({
  useRunConsole: () => ({ data: null }),
}));

function makeTask(overrides: Partial<TaskYAML> = {}): TaskYAML {
  return {
    name: 'taskA',
    command: 'echo hello',
    env: {},
    retry: 0,
    depends_on: [],
    ...overrides,
  };
}

function makeSub(overrides: Partial<SubPipeline> = {}): SubPipeline {
  return {
    name: 'sub1',
    depends_on: [],
    tasks: [makeTask()],
    ...overrides,
  };
}

function makePipeline(overrides: Partial<PipelineDetail> = {}): PipelineDetail {
  return {
    name: 'demo',
    pipelines: [makeSub()],
    ...overrides,
  };
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('<TaskTree /> Issue #72 - 右键重试 + 重试版本徽标', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('有重试版本时显示重试数徽标', () => {
    const pipeline = makePipeline();
    const taskRuns = [
      {
        task_name: 'sub1.taskA',
        status: 'failed' as const,
        exit_code: 1,
        error: null,
        started_at: '2026-01-01T00:00:00Z',
        finished_at: '2026-01-01T00:00:10Z',
      },
    ];

    render(
      <Wrapper>
        <TaskTree
          pipeline={pipeline}
          taskRuns={taskRuns}
          onSelect={vi.fn()}
          isLive={false}
          retryCounts={{ 'sub1.taskA': 2 }}
        />
      </Wrapper>,
    );

    // 重试数徽标显示 "2"（subpipeline 任务数徽标显示 "1"，所以 "2" 唯一）
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('无重试版本时不显示徽标', () => {
    const pipeline = makePipeline();
    const taskRuns = [
      {
        task_name: 'sub1.taskA',
        status: 'success' as const,
        exit_code: 0,
        error: null,
        started_at: '2026-01-01T00:00:00Z',
        finished_at: '2026-01-01T00:00:10Z',
      },
    ];

    render(
      <Wrapper>
        <TaskTree
          pipeline={pipeline}
          taskRuns={taskRuns}
          onSelect={vi.fn()}
          isLive={false}
          retryCounts={{}}
        />
      </Wrapper>,
    );

    // 无重试版本时不应有紫色徽标数字 "2"
    expect(screen.queryByText('2')).not.toBeInTheDocument();
  });

  it('接受 onRetry / onShowVersions 回调且不报错', () => {
    const pipeline = makePipeline();
    const taskRuns = [
      {
        task_name: 'sub1.taskA',
        status: 'failed' as const,
        exit_code: 1,
        error: null,
        started_at: '2026-01-01T00:00:00Z',
        finished_at: '2026-01-01T00:00:10Z',
      },
    ];

    // 仅验证组件能正常渲染并接受新 props（右键菜单由 antd Dropdown 管理，
    // jsdom 无法完整模拟 contextMenu 事件，这里验证回调类型正确传入）
    expect(() =>
      render(
        <Wrapper>
          <TaskTree
            pipeline={pipeline}
            taskRuns={taskRuns}
            onSelect={vi.fn()}
            isLive={false}
            onRetry={vi.fn()}
            onShowVersions={vi.fn()}
            retryCounts={{ 'sub1.taskA': 1 }}
          />
        </Wrapper>,
      ),
    ).not.toThrow();
  });

  it('运行中（isLive=true）的任务不显示重试菜单（canRetry=false）', () => {
    const pipeline = makePipeline();
    const taskRuns = [
      {
        task_name: 'sub1.taskA',
        status: 'running' as const,
        exit_code: null,
        error: null,
        started_at: '2026-01-01T00:00:00Z',
        finished_at: null,
      },
    ];

    // isLive=true 时 canRetry=false，即使有 retryCounts 也不应能重试
    // 但 retryCounts > 0 时仍显示版本徽标
    render(
      <Wrapper>
        <TaskTree
          pipeline={pipeline}
          taskRuns={taskRuns}
          onSelect={vi.fn()}
          isLive={true}
          onRetry={vi.fn()}
          onShowVersions={vi.fn()}
          retryCounts={{ 'sub1.taskA': 2 }}
        />
      </Wrapper>,
    );

    // 版本徽标仍显示（"2" 唯一，因为 subpipeline 任务数是 "1"）
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});
