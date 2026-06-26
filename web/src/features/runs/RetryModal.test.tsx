import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntdApp } from 'antd';
import type { ReactNode } from 'react';

// Mock API hooks
const mockUseDependencyTree = vi.fn();
const mockUseRetryRun = vi.fn();
const mockUseRetryVersions = vi.fn();
const mockUseSelectRetryReport = vi.fn();
const mockUseRetryLogs = vi.fn();

const mockUseCancelRetryRun = vi.fn();

vi.mock('@/api/runs', () => ({
  useDependencyTree: (...args: unknown[]) => mockUseDependencyTree(...args),
  useRetryRun: () => mockUseRetryRun(),
  useRetryVersions: (runId?: string) => mockUseRetryVersions(runId),
  useSelectRetryReport: () => mockUseSelectRetryReport(),
  useRetryLogs: (runId?: string, retryId?: string) => mockUseRetryLogs(runId, retryId),
  useCancelRetryRun: () => mockUseCancelRetryRun(),
}));

vi.mock('@/components/StatusTag', () => ({
  default: ({ status }: { status: string }) => <span data-testid="status-tag">{status}</span>,
}));

import RetryModal from './RetryModal';
import RetryVersionsDrawer from './RetryVersionsDrawer';
import type { RetryRecordResponse, DependencyTreeResponse, RetryVersionsResponse } from '@/types';

/** 用 QueryClient + Antd App 包裹（message API 需要 App 上下文） */
function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>{children}</AntdApp>
    </QueryClientProvider>
  );
}

/** 构造依赖树响应 */
function makeDepTree(overrides: Partial<DependencyTreeResponse> = {}): DependencyTreeResponse {
  return {
    target: 'sub.taskA',
    subpipeline: 'sub',
    tree: [
      { name: 'sub.taskUp', depends_on: [], level: 0, upstream_of_target: true, mandatory_if_upstream: true },
      { name: 'sub.taskA', depends_on: ['sub.taskUp'], level: 1, upstream_of_target: false, mandatory_if_upstream: false },
    ],
    ...overrides,
  };
}

/** 构造重试记录 */
function makeRetryRecord(overrides: Partial<RetryRecordResponse> = {}): RetryRecordResponse {
  return {
    id: 'retry-1',
    run_id: 'run-1',
    task_run_id: 'tr-1',
    task_name: 'sub.taskA',
    subpipeline_name: 'sub',
    retry_version: 1,
    status: 'success',
    command: 'echo hello',
    original_command: 'echo hello',
    log_path: '/logs/retry-1.log',
    exit_code: 0,
    error: null,
    started_at: '2026-01-01T00:00:00Z',
    finished_at: '2026-01-01T00:00:10Z',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

/** 构造重试版本响应 */
function makeVersionsResponse(
  taskName: string,
  retries: RetryRecordResponse[],
  selected: string | null = null,
): RetryVersionsResponse {
  return {
    task_retries: { [taskName]: retries },
    selected: selected ? { [taskName]: selected } : {},
  };
}

describe('<RetryModal /> Issue #72 - 重试弹窗', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDependencyTree.mockReturnValue({ data: undefined, isLoading: true });
    mockUseRetryRun.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  });

  it('展示任务名、状态和原始命令（只读）', () => {
    mockUseDependencyTree.mockReturnValue({ data: makeDepTree(), isLoading: false });

    render(
      <Wrapper>
        <RetryModal
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          taskStatus="failed"
          taskCommand="echo hello"
          onClose={vi.fn()}
        />
      </Wrapper>,
    );

    // 任务名出现在任务信息区和依赖树中
    expect(screen.getAllByText('sub.taskA').length).toBeGreaterThan(0);
    expect(screen.getByText(/echo hello/)).toBeInTheDocument();
    expect(screen.getByText(/只读/)).toBeInTheDocument();
  });

  it('展示依赖树并标记目标任务', () => {
    mockUseDependencyTree.mockReturnValue({ data: makeDepTree(), isLoading: false });

    render(
      <Wrapper>
        <RetryModal
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          taskStatus="failed"
          onClose={vi.fn()}
        />
      </Wrapper>,
    );

    // 目标任务和上游任务都显示
    expect(screen.getAllByText('sub.taskA').length).toBeGreaterThan(0);
    expect(screen.getByText('sub.taskUp')).toBeInTheDocument();
    // "目标" 标签
    expect(screen.getByText('目标')).toBeInTheDocument();
    // "上游" 标签
    expect(screen.getByText('上游')).toBeInTheDocument();
  });

  it('有上游依赖时显示"包含上游依赖"开关', () => {
    mockUseDependencyTree.mockReturnValue({ data: makeDepTree(), isLoading: false });

    render(
      <Wrapper>
        <RetryModal
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          taskStatus="failed"
          onClose={vi.fn()}
        />
      </Wrapper>,
    );

    expect(screen.getByText('包含上游依赖')).toBeInTheDocument();
    expect(screen.getByText(/将同时重跑 1 个上游任务/)).toBeInTheDocument();
  });

  it('无上游依赖时不显示"包含上游依赖"开关', () => {
    mockUseDependencyTree.mockReturnValue({
      data: {
        target: 'sub.taskA',
        subpipeline: 'sub',
        tree: [
          { name: 'sub.taskA', depends_on: [], level: 0, upstream_of_target: false, mandatory_if_upstream: false },
        ],
      },
      isLoading: false,
    });

    render(
      <Wrapper>
        <RetryModal
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          taskStatus="failed"
          onClose={vi.fn()}
        />
      </Wrapper>,
    );

    expect(screen.queryByText('包含上游依赖')).not.toBeInTheDocument();
  });

  it('确认重试时调用 mutateAsync 并传入正确的任务列表', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseRetryRun.mockReturnValue({ mutateAsync, isPending: false });
    mockUseDependencyTree.mockReturnValue({ data: makeDepTree(), isLoading: false });

    const onClose = vi.fn();
    render(
      <Wrapper>
        <RetryModal
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          taskStatus="failed"
          onClose={onClose}
        />
      </Wrapper>,
    );

    // 默认不包含上游，只重试目标任务
    const confirmBtn = screen.getByText('确认重试');
    await fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        runId: 'run-1',
        tasks: ['sub.taskA'],
        include_upstream: false,
        retry_execution_strategy: 'parallel',
      });
    });
    expect(onClose).toHaveBeenCalled();
  });
});

describe('<RetryVersionsDrawer /> Issue #72 - 版本管理', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSelectRetryReport.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockUseRetryLogs.mockReturnValue({ data: undefined, isLoading: true });
  });

  it('展示原始版本 (v0) 和重试版本（按版本号倒序）', () => {
    const v0 = {
      id: 'tr-1',
      run_id: 'run-1',
      task_run_id: 'tr-1',
      task_name: 'sub.taskA',
      subpipeline_name: 'sub',
      retry_version: 0,
      status: 'failed',
      command: '',
      original_command: '',
      log_path: '/logs/tr-1.log',
      exit_code: 1,
      error: null,
      started_at: '2026-01-01T00:00:00Z',
      finished_at: '2026-01-01T00:00:05Z',
      created_at: '2026-01-01T00:00:00Z',
    };
    const retries = [
      makeRetryRecord({ id: 'r1', retry_version: 1, status: 'failed', exit_code: 1 }),
      makeRetryRecord({ id: 'r2', retry_version: 2, status: 'success', exit_code: 0 }),
    ];
    mockUseRetryVersions.mockReturnValue({
      data: makeVersionsResponse('sub.taskA', [v0, ...retries], 'r2'),
    });

    render(
      <Wrapper>
        <RetryVersionsDrawer
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          onClose={vi.fn()}
        />
      </Wrapper>,
    );

    // 原始版本 + 两个重试版本
    expect(screen.getByText('原始版本')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.getByText('v2')).toBeInTheDocument();
    expect(screen.getByText('首次执行')).toBeInTheDocument();
    // v2 是选中的最终版本
    expect(screen.getByText('当前版本')).toBeInTheDocument();
  });

  it('无版本数据时显示空状态', () => {
    mockUseRetryVersions.mockReturnValue({
      data: { task_retries: {}, selected: {} },
    });

    render(
      <Wrapper>
        <RetryVersionsDrawer
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          onClose={vi.fn()}
        />
      </Wrapper>,
    );

    expect(screen.getByText(/暂无版本数据/)).toBeInTheDocument();
  });

  it('点击"设为最终版本"调用 selectReport', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseSelectRetryReport.mockReturnValue({ mutateAsync, isPending: false });
    const retries = [
      makeRetryRecord({ id: 'r1', retry_version: 1, status: 'success' }),
      makeRetryRecord({ id: 'r2', retry_version: 2, status: 'success' }),
    ];
    mockUseRetryVersions.mockReturnValue({
      data: makeVersionsResponse('sub.taskA', retries, 'r2'),
    });

    render(
      <Wrapper>
        <RetryVersionsDrawer
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          onClose={vi.fn()}
        />
      </Wrapper>,
    );

    // v1 不是当前选中版本，应显示"设为最终版本"按钮
    const selectButtons = screen.getAllByText('设为最终版本');
    expect(selectButtons.length).toBeGreaterThan(0);

    await fireEvent.click(selectButtons[0]);

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          runId: 'run-1',
          taskName: 'sub.taskA',
        }),
      );
    });
  });

  it('Issue #99: 设置最终版本成功后触发 onVersionsChanged', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseSelectRetryReport.mockReturnValue({ mutateAsync, isPending: false });
    const retries = [makeRetryRecord({ id: 'r1', retry_version: 1, status: 'success' })];
    mockUseRetryVersions.mockReturnValue({
      data: makeVersionsResponse('sub.taskA', retries, null),
    });
    const onVersionsChanged = vi.fn();

    render(
      <Wrapper>
        <RetryVersionsDrawer
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          onClose={vi.fn()}
          onVersionsChanged={onVersionsChanged}
        />
      </Wrapper>,
    );

    const selectButton = screen.getByText('设为最终版本');
    await fireEvent.click(selectButton);

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalled();
      expect(onVersionsChanged).toHaveBeenCalled();
    });
  });

  it('点击"查看日志"打开日志 Modal', async () => {
    const retries = [makeRetryRecord({ id: 'r1', retry_version: 1, status: 'success' })];
    mockUseRetryVersions.mockReturnValue({
      data: makeVersionsResponse('sub.taskA', retries, 'r1'),
    });
    mockUseRetryLogs.mockReturnValue({
      data: { log_path: '/logs/r1.log', content: 'log line 1\nlog line 2', exists: true },
      isLoading: false,
    });

    render(
      <Wrapper>
        <RetryVersionsDrawer
          open={true}
          runId="run-1"
          taskName="sub.taskA"
          onClose={vi.fn()}
        />
      </Wrapper>,
    );

    const viewLogBtn = screen.getByText('查看日志');
    await fireEvent.click(viewLogBtn);

    await waitFor(() => {
      expect(screen.getByText('重试日志')).toBeInTheDocument();
      expect(screen.getByText(/log line 1/)).toBeInTheDocument();
    });
  });
});
