import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from './client';
import type { ProjectResponse } from '@/types';

/** 获取所有已注册项目 */
export function useProjects() {
  return useQuery<ProjectResponse[]>({
    queryKey: ['projects'],
    queryFn: async () => {
      const res = await apiClient.get('/api/projects/');
      return res.data;
    },
  });
}

/** 获取单个项目详情（页面加载时获取项目名称） */
export function useProject(projectId: string | undefined) {
  return useQuery<ProjectResponse>({
    queryKey: ['project', projectId],
    queryFn: async () => {
      const res = await apiClient.get(`/api/projects/${encodeURIComponent(projectId!)}`);
      return res.data;
    },
    enabled: !!projectId,
  });
}

/**
 * v3 (2026-09): 网页端注册项目目录。
 * workdir 必须是 server 所在机器上已存在的绝对路径（后端严格校验）；
 * 注册成功后刷新项目列表与流水线列表，让新项目立即出现在列表中。
 */
export function useRegisterProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ workdir, name }: { workdir: string; name?: string }) => {
      const res = await apiClient.post('/api/projects/', { workdir, name: name ?? '' });
      return res.data as ProjectResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
  });
}
