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

// v3 (2026-09): 网页端新建/重命名/删除流水线与文件夹
// 统一在成功后失效 ['pipelines'] 列表缓存，列表页自动刷新。

/** 新建流水线响应 */
export interface CreatePipelineResult {
  status: string;
  file: string;
  definition_id: string | null;
}

/**
 * 新建流水线。
 * 设计决策：走 POST 而非复用 PUT —— 后端 POST 对已存在文件返回 409，
 * 避免用户重名时静默覆盖已有流水线。
 * projectId 作为 mutation 变量传入：列表页/弹窗可能在多个项目间操作。
 */
export function useCreatePipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      file,
      content,
    }: {
      projectId: string;
      file: string;
      content: string;
    }) => {
      const res = await apiClient.post(
        `/api/pipelines/by-file/${encodeURIComponent(projectId)}`,
        { file, content },
      );
      return res.data as CreatePipelineResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
  });
}

/** 重命名/移动流水线文件（不修改 YAML 内的 name） */
export function useRenamePipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      file,
      newFile,
    }: {
      projectId: string;
      file: string;
      newFile: string;
    }) => {
      const res = await apiClient.patch(
        `/api/pipelines/by-file/${encodeURIComponent(projectId)}`,
        { file, new_file: newFile },
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
  });
}

/** 删除流水线文件（后端软删除定义，保留运行历史） */
export function useDeletePipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ projectId, file }: { projectId: string; file: string }) => {
      const res = await apiClient.delete(
        `/api/pipelines/by-file/${encodeURIComponent(projectId)}`,
        { params: { file } },
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
  });
}

/** 新建流水线文件夹（支持多级路径） */
export function useCreateFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ projectId, folder }: { projectId: string; folder: string }) => {
      const res = await apiClient.post(
        `/api/pipelines/folders/${encodeURIComponent(projectId)}`,
        { folder },
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
  });
}

/** 重命名/移动流水线文件夹 */
export function useRenameFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      folder,
      newFolder,
    }: {
      projectId: string;
      folder: string;
      newFolder: string;
    }) => {
      const res = await apiClient.patch(
        `/api/pipelines/folders/${encodeURIComponent(projectId)}`,
        { folder, new_folder: newFolder },
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
  });
}

/** 删除流水线文件夹；非空时必须 recursive=true（后端强校验） */
export function useDeleteFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      folder,
      recursive,
    }: {
      projectId: string;
      folder: string;
      recursive?: boolean;
    }) => {
      const res = await apiClient.delete(
        `/api/pipelines/folders/${encodeURIComponent(projectId)}`,
        { params: { folder, recursive: recursive ?? false } },
      );
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
  });
}
