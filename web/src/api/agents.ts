import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import apiClient from './client';
import type { AgentCheckResult, AgentStatus, AgentWithConfig, AgentHostInfo, PendingCommandItem } from '@/types';

/** 新增服务器请求体（字段与后端 AgentConfigCreateRequest 对齐） */
export interface AgentCreatePayload {
  project_id: string;
  id: string;
  name?: string;
  description?: string;
  type?: string;
  host?: string;
  port?: number;
  username?: string;
  credential_id?: string;
  max_parallel?: number;
  execution_agent?: boolean;
  agent_auto_bootstrap?: boolean;
  /** agent 回连服务端的地址；留空由服务端自动探测（远端不可达时必填） */
  server_ws_host?: string;
}

/** 编辑服务器请求体（id/project 不可改） */
export type AgentUpdatePayload = Omit<AgentCreatePayload, 'project_id' | 'id'>;

/** 新增服务器：成功后刷新列表（后端会清理自身缓存） */
export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: AgentCreatePayload) => {
      const res = await apiClient.post('/api/agents/', payload);
      return res.data as { agent_id: string };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents', 'all'] });
      qc.invalidateQueries({ queryKey: ['agents', 'list'] });
    },
  });
}

/** 编辑服务器：仅提交变更字段，未提交的字段由后端保留 */
export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      agentId,
      payload,
    }: {
      projectId: string;
      agentId: string;
      payload: AgentUpdatePayload;
    }) => {
      const res = await apiClient.put(
        `/api/agents/${encodeURIComponent(projectId)}/${encodeURIComponent(agentId)}`,
        payload,
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents', 'all'] });
      qc.invalidateQueries({ queryKey: ['agents', 'list'] });
      qc.invalidateQueries({ queryKey: ['agents', 'status'] });
    },
  });
}

/** 删除服务器：被流水线引用时后端返回 409，由调用方展示错误 */
export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ projectId, agentId }: { projectId: string; agentId: string }) => {
      await apiClient.delete(
        `/api/agents/${encodeURIComponent(projectId)}/${encodeURIComponent(agentId)}`,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents', 'all'] });
      qc.invalidateQueries({ queryKey: ['agents', 'list'] });
    },
  });
}

/** 测试连接（仅对已保存的 agent 可用：后端按 agent_id 读取配置与凭据） */
export function useTryConnectAgent() {
  return useMutation({
    mutationFn: async (agentId: string) => {
      const res = await apiClient.post<AgentCheckResult>(
        '/api/agents/try-connect',
        { agent_id: agentId, timeout: 8 },
        { timeout: 15000 },
      );
      return res.data;
    },
  });
}

/** 部署/引导 agent（未连接时） */
export function useDeployAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (agentId: string) => {
      const res = await apiClient.post<{ success: boolean; agent_id: string; message?: string }>(
        '/api/agents/deploy',
        { agent_id: agentId, timeout: 30 },
        // v2 (2026-09): 后端握手等待固定 60s（BOOTSTRAP_TIMEOUT），默认 30s 的全局超时
        // 会让 UI 先断开、看不到服务端返回的失败原因；这里放大到 90s 覆盖握手 + SSH 上传耗时
        { timeout: 90000 },
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

/** 强制更新已部署 agent（重新上传二进制并重启） */
export function useUpdateDeployAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (agentId: string) => {
      const res = await apiClient.post<{ success: boolean; agent_id: string; message?: string }>(
        '/api/agents/update-deploy',
        { agent_id: agentId, timeout: 60 },
        { timeout: 90000 },
      );
      return res.data;
    },
    onSuccess: (data, agentId) => {
      if (data?.success) {
        message.success(`Agent ${agentId} 更新部署成功`);
      } else {
        message.warning(`Agent ${agentId} 更新部署未完成：${data?.message ?? '请检查 agent 端日志'}`);
      }
      qc.invalidateQueries({ queryKey: ['agents', 'all'] });
      qc.invalidateQueries({ queryKey: ['agents', 'list'] });
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }, agentId) => {
      const detail = err?.response?.data?.detail ?? err?.message ?? '未知错误';
      message.error(`Agent ${agentId} 更新部署失败：${detail}`);
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
    // 保留上一次成功的列表数据：再次进入 /servers 时（缓存未失效）立即展示老数据，
    // 后台静默刷新，避免"每次点进去都是加载中、啥都没有"
    placeholderData: keepPreviousData,
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

/** 获取 agent 正在执行的命令列表 */
export function usePendingCommands(agentId: string | undefined, enabled = false) {
  return useQuery<PendingCommandItem[]>({
    queryKey: ['agents', 'pending', agentId],
    queryFn: async () => {
      const res = await apiClient.get<PendingCommandItem[]>(`/api/agents/${agentId}/pending-commands`);
      return res.data;
    },
    enabled: !!agentId && enabled,
    refetchInterval: 3000,
  });
}
