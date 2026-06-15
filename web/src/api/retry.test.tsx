import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  useRetryRun,
  useRetryVersions,
  useRetryCommand,
  useUpdateRetryCommand,
  useDependencyTree,
  useSelectRetryReport,
  useBatchSelectRetryReport,
  useRetryLogs,
} from './runs';

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();

vi.mock('./client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: vi.fn(),
  },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

describe('retry API hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useRetryRun', () => {
    it('triggers retry and invalidates queries', async () => {
      const mockResponse = {
        run_id: 'run1',
        retry_records: [
          { id: 'rec1', task_name: 'deploy.step1', retry_version: 1, status: 'success', command: 'echo ok', log_path: '/tmp/r.log' },
        ],
      };
      mockPost.mockResolvedValueOnce({ data: mockResponse });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryRun(), { wrapper });

      await result.current.mutateAsync({
        runId: 'run1',
        tasks: ['deploy.step1'],
      });

      expect(mockPost).toHaveBeenCalledWith('/api/runs/run1/retry', {
        tasks: ['deploy.step1'],
        subpipeline: undefined,
        include_upstream: false,
        command_overrides: undefined,
      });
    });

    it('sends include_upstream and command_overrides', async () => {
      mockPost.mockResolvedValueOnce({ data: { run_id: 'run1', retry_records: [] } });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryRun(), { wrapper });

      await result.current.mutateAsync({
        runId: 'run1',
        tasks: ['deploy.step2'],
        include_upstream: true,
        command_overrides: { 'deploy.step2': 'echo fixed' },
      });

      expect(mockPost).toHaveBeenCalledWith('/api/runs/run1/retry', {
        tasks: ['deploy.step2'],
        subpipeline: undefined,
        include_upstream: true,
        command_overrides: { 'deploy.step2': 'echo fixed' },
      });
    });

    it('sends subpipeline instead of tasks', async () => {
      mockPost.mockResolvedValueOnce({ data: { run_id: 'run1', retry_records: [] } });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryRun(), { wrapper });

      await result.current.mutateAsync({
        runId: 'run1',
        subpipeline: 'deploy',
      });

      expect(mockPost).toHaveBeenCalledWith('/api/runs/run1/retry', {
        tasks: undefined,
        subpipeline: 'deploy',
        include_upstream: false,
        command_overrides: undefined,
      });
    });
  });

  describe('useRetryVersions', () => {
    it('fetches retry versions', async () => {
      const mockData = {
        task_retries: {
          'deploy.step1': [{ id: 'rec1', retry_version: 1, status: 'success' }],
        },
        selected: { 'deploy.step1': 'rec1' },
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryVersions('run1'), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.task_retries['deploy.step1']).toHaveLength(1);
      expect(result.current.data?.selected['deploy.step1']).toBe('rec1');
    });

    it('does not fetch when runId is undefined', () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryVersions(undefined), { wrapper });

      expect(result.current.fetchStatus).toBe('idle');
      expect(mockGet).not.toHaveBeenCalled();
    });
  });

  describe('useRetryCommand', () => {
    it('fetches retry command', async () => {
      const mockData = {
        retry_id: 'rec1',
        task_name: 'deploy.step1',
        original_command: 'echo ${env.cmd}',
        resolved_command: 'echo hello',
        variables: { cmd: 'hello' },
        editable: true,
        status: 'pending',
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryCommand('run1', 'rec1'), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.editable).toBe(true);
      expect(result.current.data?.resolved_command).toBe('echo hello');
    });

    it('does not fetch when ids are missing', () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryCommand('run1', undefined), { wrapper });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useUpdateRetryCommand', () => {
    it('updates retry command', async () => {
      mockPut.mockResolvedValueOnce({ data: { retry_id: 'rec1', command: 'echo updated' } });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useUpdateRetryCommand(), { wrapper });

      await result.current.mutateAsync({
        runId: 'run1',
        retryId: 'rec1',
        command: 'echo updated',
      });

      expect(mockPut).toHaveBeenCalledWith('/api/runs/run1/retry/rec1/command', {
        command: 'echo updated',
      });
    });
  });

  describe('useDependencyTree', () => {
    it('fetches dependency tree', async () => {
      const mockData = {
        target: 'deploy.step2',
        subpipeline: 'deploy',
        tree: [
          { name: 'deploy.step1', depends_on: [], level: 0, upstream_of_target: true, mandatory_if_upstream: true },
          { name: 'deploy.step2', depends_on: ['deploy.step1'], level: 1, upstream_of_target: false, mandatory_if_upstream: false },
        ],
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useDependencyTree('run1', 'deploy.step2'), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.tree).toHaveLength(2);
      expect(result.current.data?.tree[0].upstream_of_target).toBe(true);
    });

    it('does not fetch when params are missing', () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useDependencyTree('run1', undefined), { wrapper });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useSelectRetryReport', () => {
    it('selects retry report', async () => {
      mockPost.mockResolvedValueOnce({ data: { task_name: 'deploy.step1', selected_retry_id: 'rec1' } });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useSelectRetryReport(), { wrapper });

      await result.current.mutateAsync({
        runId: 'run1',
        retryId: 'rec1',
        taskName: 'deploy.step1',
        selectedRetryId: 'rec1',
      });

      expect(mockPost).toHaveBeenCalledWith('/api/runs/run1/retry/rec1/select-report', {
        task_name: 'deploy.step1',
        selected_retry_id: 'rec1',
      });
    });
  });

  describe('useBatchSelectRetryReport', () => {
    it('batch selects retry reports', async () => {
      mockPost.mockResolvedValueOnce({ data: { selected: { 'deploy.step1': 'rec1', 'deploy.step2': 'rec2' } } });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useBatchSelectRetryReport(), { wrapper });

      await result.current.mutateAsync({
        runId: 'run1',
        selections: { 'deploy.step1': 'rec1', 'deploy.step2': 'rec2' },
      });

      expect(mockPost).toHaveBeenCalledWith('/api/runs/run1/retry/select-report', {
        selections: { 'deploy.step1': 'rec1', 'deploy.step2': 'rec2' },
      });
    });
  });

  describe('useRetryLogs', () => {
    it('fetches retry logs', async () => {
      const mockData = { log_path: '/tmp/r.log', content: 'hello world', exists: true };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryLogs('run1', 'rec1'), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.content).toBe('hello world');
      expect(result.current.data?.exists).toBe(true);
    });

    it('fetches retry logs with tail', async () => {
      const mockData = { log_path: '/tmp/r.log', content: 'last line', exists: true };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryLogs('run1', 'rec1', 10), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(mockGet).toHaveBeenCalledWith('/api/runs/run1/retry/rec1/logs?tail=10');
    });

    it('does not fetch when ids are missing', () => {
      const { wrapper } = createWrapper();
      const { result } = renderHook(() => useRetryLogs('run1', undefined), { wrapper });

      expect(result.current.fetchStatus).toBe('idle');
    });
  });
});
