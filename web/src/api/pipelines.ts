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

/** 通过 definition_id 获取单个流水线详情 */
export function usePipelineById(definitionId: string | undefined) {
  return useQuery<PipelineDetail>({
    queryKey: ['pipeline', definitionId],
    queryFn: async () => {
      const res = await apiClient.get(`/api/pipelines/by-id/${encodeURIComponent(definitionId!)}`);
      return res.data;
    },
    enabled: !!definitionId,
  });
}

/** 通过 definition_id 保存 pipeline YAML */
export function useSavePipelineById(definitionId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (content: string) => {
      const res = await apiClient.put(`/api/pipelines/by-id/${encodeURIComponent(definitionId!)}`, { content });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipeline', definitionId] });
    },
  });
}
