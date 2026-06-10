import { useQuery } from '@tanstack/react-query';
import apiClient from './client';
import type { PipelineListResponse, PipelineDetail } from '@/types';

/** 获取流水线列表 */
export function usePipelines(projectId?: string | null) {
  return useQuery<PipelineListResponse>({
    queryKey: ['pipelines', projectId],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (projectId) params.project_id = projectId;
      const res = await apiClient.get('/api/pipelines/', { params });
      return res.data;
    },
  });
}

/** 获取单个流水线详情 */
export function usePipeline(file: string | undefined, projectId?: string | null) {
  return useQuery<PipelineDetail>({
    queryKey: ['pipeline', file, projectId],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (projectId) params.project_id = projectId;
      const res = await apiClient.get(`/api/pipelines/${encodeURIComponent(file!)}`, { params });
      return res.data;
    },
    enabled: !!file,
  });
}
