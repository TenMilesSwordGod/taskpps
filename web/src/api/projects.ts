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
