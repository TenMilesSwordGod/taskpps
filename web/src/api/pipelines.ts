import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from './client';
import type { PipelineListResponse, PipelineDetail } from '@/types';

/** 获取流水线列表 */
export function usePipelines() {
  return useQuery<PipelineListResponse>({
    queryKey: ['pipelines'],
    queryFn: async () => {
      const res = await apiClient.get('/api/pipelines/');
      return res.data;
    },
  });
}

/** 获取单个流水线详情 */
export function usePipeline(file: string | undefined) {
  return useQuery<PipelineDetail>({
    queryKey: ['pipeline', file],
    queryFn: async () => {
      const res = await apiClient.get(`/api/pipelines/${encodeURIComponent(file!)}`);
      return res.data;
    },
    enabled: !!file,
  });
}

/** 保存 pipeline YAML */
export function useSavePipeline(file: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (content: string) => {
      const res = await apiClient.put(`/api/pipelines/${encodeURIComponent(file!)}`, { content });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline', file] });
    },
  });
}
