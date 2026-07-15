import { useQuery } from '@tanstack/react-query';
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
