import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from './client';
import type { CredentialView } from '@/types';

/**
 * 凭据管理 API hooks（仅管理员可用）。
 *
 * 设计决策：
 * - 查询按项目维度缓存（key 含 projectId），新增/编辑/删除后 invalidate 对应项目，
 *   AgentFormModal 里的凭据下拉会自动刷新，无需手动同步。
 * - 更新语义由后端定义：password 字段省略=不修改、空串=清除；前端表单据此构造 payload。
 */

export interface CredentialCreatePayload {
  project_id: string;
  id: string;
  name?: string;
  description?: string;
  type?: string;
  username?: string;
  password?: string;
  key_path?: string;
}

export interface CredentialUpdatePayload {
  name?: string;
  description?: string;
  type?: string;
  username?: string;
  password?: string;
  key_path?: string;
}

/** 获取项目下的凭据元数据列表（含 has_password 标记，无任何密码明文） */
export function useCredentials(projectId: string | undefined, enabled = true) {
  return useQuery<CredentialView[]>({
    queryKey: ['credentials', projectId],
    queryFn: async () => {
      const res = await apiClient.get('/api/credentials/', { params: { project_id: projectId } });
      return Array.isArray(res.data) ? (res.data as CredentialView[]) : [];
    },
    enabled: !!projectId && enabled,
    staleTime: 5000,
  });
}

export function useCreateCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CredentialCreatePayload) => {
      const res = await apiClient.post<CredentialView>('/api/credentials/', payload);
      return res.data;
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['credentials', data.project_id] });
    },
  });
}

export function useUpdateCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      credentialId,
      payload,
    }: {
      projectId: string;
      credentialId: string;
      payload: CredentialUpdatePayload;
    }) => {
      const res = await apiClient.put<CredentialView>(
        `/api/credentials/${encodeURIComponent(projectId)}/${encodeURIComponent(credentialId)}`,
        payload,
      );
      return res.data;
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['credentials', data.project_id] });
    },
  });
}

export function useDeleteCredential() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ projectId, credentialId }: { projectId: string; credentialId: string }) => {
      await apiClient.delete(
        `/api/credentials/${encodeURIComponent(projectId)}/${encodeURIComponent(credentialId)}`,
      );
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['credentials', variables.projectId] });
    },
  });
}
