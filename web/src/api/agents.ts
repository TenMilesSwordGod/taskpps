import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import apiClient from './client';
import type { AgentStatus, AgentWithConfig, AgentHostInfo } from '@/types';

/** 部署/引导 agent（未连接时） */
export function useDeployAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (agentId: string) => {
      const res = await apiClient.post<{ success: boolean; agent_id: string; message?: string }>(
        '/api/agents/deploy',
        { agent_id: agentId, timeout: 30 },
      );
      return res.data;
    },
    onSuccess: (data, agentId) => {
      if (data?.success) {
        message.success(`Agent ${agentId} 部署成功`);
      } else {
        message.warning(`Agent ${agentId} 部署未完成：${data?.message ?? '请检查 agent 端日志'}`);
      }
      qc.invalidateQueries({ queryKey: ['agents', 'all'] });
      qc.invalidateQueries({ queryKey: ['agents', 'list'] });
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }, agentId) => {
      const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误';
      message.error(`Agent ${agentId} 部署失败：${detail}`);
    },
  });
}

/** 获取 agent host 详细信息（CPU/内存/磁盘/内核） */
export function useAgentHostInfo(agentId: string | undefined) {
  return useQuery<AgentHostInfo>({
    queryKey: ['agentHostInfo', agentId],
    queryFn: async () => {
      const res = await apiClient.get<AgentHostInfo>(`/api/agents/${agentId}/host-info`);
      return res.data;
    },
    enabled: !!agentId,
    retry: 0,
    refetchOnWindowFocus: false,
  });
}

/** 获取所有已连接 agent（5s 轮询） */
export function useAgents(enabled = true) {
  return useQuery<AgentStatus[]>({
    queryKey: ['agents', 'list'],
    queryFn: async () => {
      const res = await apiClient.get('/api/agents/list');
      return Array.isArray(res.data) ? (res.data as AgentStatus[]) : [];
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
      const res = await apiClient.get('/api/agents/all');
      // 防御性：后端未重启/出错时可能返回 {detail: "..."} 或非数组
      return Array.isArray(res.data) ? (res.data as AgentWithConfig[]) : [];
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
