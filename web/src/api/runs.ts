import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from './client';
import type {
  RunListResponse,
  RunResponse,
  RunStatsResponse,
  ResultPageResponse,
  RetryRunResponse,
  RetryVersionsResponse,
  RetryCommandResponse,
  DependencyTreeResponse,
  PipelineDetail,
  RetryExecutionStrategy,
  ArtifactListResponse,
} from '@/types';

/** 历史日志响应（REST 模式） */
export interface RunLogsResponse {
  logs: Record<string, string>;
}

/** 获取运行列表 */
export function useRuns(params?: { pipeline?: string; status?: string; limit?: number }) {
  return useQuery<RunListResponse>({
    queryKey: ['runs', params],
    queryFn: async () => {
      const cleanParams: Record<string, string | number> = {};
      if (params?.pipeline) cleanParams.pipeline = params.pipeline;
      if (params?.status) cleanParams.status = params.status;
      if (params?.limit) cleanParams.limit = params.limit;
      const res = await apiClient.get('/api/runs/', { params: cleanParams });
      return res.data;
    },
    refetchInterval: (query) => {
      const hasActive = query.state.data?.items.some(
        (r) => r.status === 'running' || r.status === 'pending',
      );
      return hasActive ? 3000 : false;
    },
  });
}

/** 获取运行状态统计 */
export function useRunStats(params?: { pipeline?: string; project_id?: string }) {
  return useQuery<RunStatsResponse>({
    queryKey: ['runStats', params],
    queryFn: async () => {
      const cleanParams: Record<string, string> = {};
      if (params?.pipeline) cleanParams.pipeline = params.pipeline;
      if (params?.project_id) cleanParams.project_id = params.project_id;
      const res = await apiClient.get('/api/runs/stats', { params: cleanParams });
      return res.data;
    },
  });
}

/** 获取单个运行详情 */
export function useRun(id: string | undefined) {
  return useQuery<RunResponse>({
    queryKey: ['run', id],
    queryFn: async () => {
      const res = await apiClient.get(`/api/runs/${id}`);
      return res.data;
    },
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'running' || status === 'pending') return 1000;
      return false;
    },
  });
}

/** 创建运行 */
export function useCreateRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: { definition_id: string; params?: Record<string, unknown>; project_id?: string | null }) => {
      const res = await apiClient.post('/api/runs/', body);
      return res.data as { id: string; pipeline_name: string; status: string };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] });
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
  });
}

/** 取消运行 */
export function useCancelRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (id: string) => {
      const res = await apiClient.post(`/api/runs/${id}/cancel`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] });
      queryClient.invalidateQueries({ queryKey: ['run'] });
    },
  });
}

/** 获取历史日志（非 SSE，用于已完成/失败等运行） */
export function useRunLogs(runId: string | undefined) {
  return useQuery<RunLogsResponse>({
    queryKey: ['runLogs', runId],
    queryFn: async () => {
      const res = await apiClient.get(`/api/runs/${runId}/logs`);
      return res.data;
    },
    enabled: !!runId,
  });
}

/** 清理历史运行响应 */
export interface CleanRunsResponse {
  deleted_runs: number;
  deleted_logs: number;
}

/** 清理历史运行参数 */
export interface CleanRunsParams {
  older_than?: number;
  keep?: number;
  force?: boolean;
}

/** 清理历史运行 */
export function useCleanRuns() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: CleanRunsParams) => {
      const res = await apiClient.delete<CleanRunsResponse>('/api/runs/', { params });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] });
    },
  });
}

/** 删除单个运行 */
export function useDeleteRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (runId: string) => {
      const res = await apiClient.delete(`/api/runs/${runId}`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] });
    },
  });
}

/** Pipeline console 日志（engine 写入的结构化 ERROR/WARN 日志） */
export interface RunConsoleResponse {
  log_path: string;
  content: string;
  lines: number;
  exists: boolean;
}

export function useRunConsole(runId: string | undefined, tail?: number) {
  return useQuery<RunConsoleResponse>({
    queryKey: ['runConsole', runId, tail],
    queryFn: async () => {
      const res = await apiClient.get<RunConsoleResponse>(
        `/api/runs/${runId}/console${tail ? `?tail=${tail}` : ''}`,
      );
      return res.data;
    },
    enabled: !!runId,
  });
}

/** 触发重试 */
export function useRetryRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: {
      runId: string;
      tasks?: string[];
      subpipeline?: string;
      include_upstream?: boolean;
      command_overrides?: Record<string, string>;
      retry_execution_strategy?: RetryExecutionStrategy;
    }) => {
      const res = await apiClient.post<RetryRunResponse>(
        `/api/runs/${params.runId}/retry`,
        {
          tasks: params.tasks,
          subpipeline: params.subpipeline,
          include_upstream: params.include_upstream ?? false,
          command_overrides: params.command_overrides,
          retry_execution_strategy: params.retry_execution_strategy ?? 'parallel',
        },
      );
      return res.data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['run', variables.runId] });
      queryClient.invalidateQueries({ queryKey: ['retryVersions', variables.runId] });
    },
  });
}

/** 取消正在进行的重试 */
export function useCancelRetryRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (runId: string) => {
      const res = await apiClient.post<{ status: string; run_id: string }>(
        `/api/runs/${runId}/retry/cancel`,
      );
      return res.data;
    },
    onSuccess: (_data, runId) => {
      queryClient.invalidateQueries({ queryKey: ['run', runId] });
      queryClient.invalidateQueries({ queryKey: ['retryVersions', runId] });
    },
  });
}

/** 获取历史运行时的流水线快照（执行时的版本） */
export function usePipelineSnapshot(runId: string | undefined) {
  return useQuery<PipelineDetail>({
    queryKey: ['pipelineSnapshot', runId],
    queryFn: async () => {
      const res = await apiClient.get(`/api/runs/${runId}/pipeline-snapshot`);
      return res.data;
    },
    enabled: !!runId,
    staleTime: Infinity,
  });
}

/** 获取重试版本列表 */
export function useRetryVersions(runId: string | undefined) {
  return useQuery<RetryVersionsResponse>({
    queryKey: ['retryVersions', runId],
    queryFn: async () => {
      const res = await apiClient.get<RetryVersionsResponse>(`/api/runs/${runId}/retry/versions`);
      return res.data;
    },
    enabled: !!runId,
  });
}

/** 获取重试命令 */
export function useRetryCommand(runId: string | undefined, retryId: string | undefined) {
  return useQuery<RetryCommandResponse>({
    queryKey: ['retryCommand', runId, retryId],
    queryFn: async () => {
      const res = await apiClient.get<RetryCommandResponse>(
        `/api/runs/${runId}/retry/${retryId}/command`,
      );
      return res.data;
    },
    enabled: !!runId && !!retryId,
  });
}

/** 更新重试命令 */
export function useUpdateRetryCommand() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: { runId: string; retryId: string; command: string }) => {
      const res = await apiClient.put<{ retry_id: string; command: string }>(
        `/api/runs/${params.runId}/retry/${params.retryId}/command`,
        { command: params.command },
      );
      return res.data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['retryCommand', variables.runId, variables.retryId] });
    },
  });
}

/** 获取依赖树 */
export function useDependencyTree(runId: string | undefined, task: string | undefined) {
  return useQuery<DependencyTreeResponse>({
    queryKey: ['dependencyTree', runId, task],
    queryFn: async () => {
      const res = await apiClient.get<DependencyTreeResponse>(
        `/api/runs/${runId}/retry/dependency-tree`,
        { params: { task } },
      );
      return res.data;
    },
    enabled: !!runId && !!task,
  });
}

/** 选择重试报告 */
export function useSelectRetryReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: {
      runId: string;
      retryId: string;
      taskName: string;
      selectedRetryId: string | null;
    }) => {
      const res = await apiClient.post(
        `/api/runs/${params.runId}/retry/${params.retryId}/select-report`,
        {
          task_name: params.taskName,
          selected_retry_id: params.selectedRetryId,
        },
      );
      return res.data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['retryVersions', variables.runId] });
      queryClient.invalidateQueries({ queryKey: ['run', variables.runId] });
    },
  });
}

/** 批量选择重试报告 */
export function useBatchSelectRetryReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: {
      runId: string;
      selections: Record<string, string>;
    }) => {
      const res = await apiClient.post(
        `/api/runs/${params.runId}/retry/select-report`,
        { selections: params.selections },
      );
      return res.data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['retryVersions', variables.runId] });
      queryClient.invalidateQueries({ queryKey: ['run', variables.runId] });
    },
  });
}

/** 获取重试日志 */
export function useRetryLogs(runId: string | undefined, retryId: string | undefined, tail?: number) {
  return useQuery<{ log_path: string; content: string; exists: boolean }>({
    queryKey: ['retryLogs', runId, retryId, tail],
    queryFn: async () => {
      const params = tail ? `?tail=${tail}` : '';
      const res = await apiClient.get(`/api/runs/${runId}/retry/${retryId}/logs${params}`);
      return res.data;
    },
    enabled: !!runId && !!retryId,
  });
}

/** 获取运行结果页 */
export function useResultPage(runId: string | undefined) {
  return useQuery<ResultPageResponse>({
    queryKey: ['resultPage', runId],
    queryFn: async () => {
      const res = await apiClient.get<ResultPageResponse>(`/api/runs/${runId}/result`);
      return res.data;
    },
    enabled: !!runId,
    staleTime: Infinity,
  });
}

/** 获取运行 artifacts 列表 */
export function useArtifacts(runId: string | undefined) {
  return useQuery<ArtifactListResponse>({
    queryKey: ['artifacts', runId],
    queryFn: async () => {
      const res = await apiClient.get(`/api/runs/${runId}/artifacts`);
      return res.data;
    },
    enabled: !!runId,
  });
}
