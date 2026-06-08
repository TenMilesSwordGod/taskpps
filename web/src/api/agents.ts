import { useQuery } from '@tanstack/react-query';
import apiClient from './client';
import type { AgentStatus, AgentWithConfig } from '@/types';

/** 获取所有已连接 agent（5s 轮询） */
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

/** 获取所有 yaml 配置的 agent + 实时连接状态（含离线） */
export function useAgentsWithConfig(enabled = true) {
  return useQuery<AgentWithConfig[]>({
    queryKey: ['agents', 'all'],
    queryFn: async () => {
      const res = await apiClient.get<AgentWithConfig[]>('/api/agents/all');
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
