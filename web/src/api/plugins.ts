import { useQuery } from '@tanstack/react-query';
import apiClient from './client';
import type { PluginResponse } from '@/types';

/** 获取所有插件 */
export function usePlugins(type?: string) {
  return useQuery<PluginResponse[]>({
    queryKey: ['plugins', type],
    queryFn: async () => {
      const params = type ? { type } : {};
      const res = await apiClient.get('/api/plugins/', { params });
      return res.data;
    },
  });
}

/** 获取单个插件详情 */
export function usePlugin(name: string | undefined) {
  return useQuery<PluginResponse>({
    queryKey: ['plugin', name],
    queryFn: async () => {
      const res = await apiClient.get(`/api/plugins/${name}`);
      return res.data;
    },
    enabled: !!name,
  });
}
