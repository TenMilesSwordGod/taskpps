import { useQuery } from '@tanstack/react-query';
import apiClient from './client';
import type { AgentStatus } from '@/types';

/** 获取在线 agent 列表（每 5 秒轮询） */
export function useAgents(enabled = true) {
  return useQuery<AgentStatus[]>({
    queryKey: ['agents', 'list'],
    queryFn: async () => {
      const res = await apiClient.get<AgentStatus[]>('/api/agents/list');
      return res.data;
    },
    enabled,
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    staleTime: 2000,
  });
}

/** 获取指定 agent 状态 */
export function useAgentStatus(agentId: string | undefined) {
  return useQuery<AgentStatus>({
    queryKey: ['agents', 'status', agentId],
    queryFn: async () => {
      const res = await apiClient.get<AgentStatus>(`/api/agents/status/${agentId}`);
      return res.data;
    },
    enabled: !!agentId,
    refetchInterval: 5000,
  });
}
