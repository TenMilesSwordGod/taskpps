import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from './client';
import type { PipelineListResponse, PipelineDetail } from '@/types';

/** 通过文件路径加载的 pipeline 数据 */
export interface PipelineByFile {
  name: string;
  file: string;
  raw_content: string;
}

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
export function usePipelineById(definitionId: string | undefined, projectId?: string | null) {
  return useQuery<PipelineDetail>({
    queryKey: ['pipeline', definitionId],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (projectId) params.project_id = projectId;
      const res = await apiClient.get(`/api/pipelines/by-id/${encodeURIComponent(definitionId!)}`, { params });
      return res.data;
    },
    enabled: !!definitionId,
  });
}

// v2 (2026-07): issue #195 补充 — 按文件路径加载 pipeline YAML
// 非法 pipeline 无 definition_id，用此 hook 直接从文件系统读取原始内容
/** 通过文件路径获取原始 YAML 内容 */
export function usePipelineByFile(projectId: string | undefined, file: string | undefined) {
  return useQuery<PipelineByFile>({
    queryKey: ['pipeline-file', projectId, file],
    queryFn: async () => {
      const res = await apiClient.get(`/api/pipelines/by-file/${encodeURIComponent(projectId!)}`, {
        params: { file },
      });
      return res.data;
    },
    enabled: !!projectId && !!file,
    retry: 1,
  });
}

// v2 (2026-07): issue #195 补充 — 按文件路径保存 pipeline YAML
// 非法 pipeline 无 definition_id，用此 mutation 保存
/** 通过文件路径保存 pipeline YAML */
export function useSavePipelineByFile(projectId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, content }: { file: string; content: string }) => {
      const res = await apiClient.put(`/api/pipelines/by-file/${encodeURIComponent(projectId!)}`, { file, content });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
      queryClient.invalidateQueries({ queryKey: ['pipeline-file'] });
    },
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
