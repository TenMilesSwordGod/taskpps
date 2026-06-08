import { useQuery } from '@tanstack/react-query';
import apiClient from './client';
import type { HealthResponse } from '@/types';

/** 健康检查 */
export function useHealthCheck() {
  const { data, isLoading, refetch } = useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: async () => {
      const res = await apiClient.get('/api/health');
      return res.data;
    },
    refetchInterval: 30000,
  });

  return { data, isLoading, refetch };
}
