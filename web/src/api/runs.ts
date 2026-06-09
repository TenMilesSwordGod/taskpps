import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from './client';
import type { RunListResponse, RunResponse } from '@/types';

/** 历史日志响应（REST 模式） */
export interface RunLogsResponse {
  logs: Record<string, string>;
}

/** 获取运行列表 */
export function useRuns(params?: { pipeline?: string; status?: string; limit?: number }) {
  return useQuery<RunListResponse>({
    queryKey: ['runs', params],
    queryFn: async () => {
      const res = await apiClient.get('/api/runs/', { params });
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
      if (status === 'running' || status === 'pending') return 3000;
      return false;
    },
  });
}

/** 创建运行 */
export function useCreateRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (body: { pipeline: string; params?: Record<string, unknown> }) => {
      const res = await apiClient.post('/api/runs/', body);
      return res.data as { id: string; pipeline_name: string; status: string };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] });
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
