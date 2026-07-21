import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient, { getToken, setToken, clearToken } from './client';

/**
 * 认证 API + React Query hooks。
 *
 * 设计决策：
 * - 用 React Query 管理 /me 查询缓存，登录/登出后自动 invalidate。
 * - token 持久化在 localStorage（client.ts 管理），hooks 只负责 API 调用 + 缓存协调。
 * - 注册成功不自动登录（spec 明确：引导去登录页）。
 */

/** 用户信息（后端 UserResponse，不含 password_hash） */
export interface AuthUser {
  id: number;
  username: string;
  nickname: string;
  role: string;
  avatar: string;
  is_active: boolean;
}

/** 登录响应 */
export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

/** 注册请求 */
export interface RegisterRequest {
  username: string;
  nickname: string;
  password: string;
}

/** 登录请求 */
export interface LoginRequest {
  username: string;
  password: string;
  /** 勾选后 token 有效期 30 天（默认 24 小时） */
  remember_me?: boolean;
}

/** 修改密码请求 */
export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}

// ---------- 基础 API 函数 ----------

/** 注册新用户（不自动登录） */
export async function registerUser(data: RegisterRequest): Promise<AuthUser> {
  const res = await apiClient.post('/api/v1/auth/register', data);
  return res.data;
}

/** 登录：返回 JWT + 用户信息 */
export async function loginUser(data: LoginRequest): Promise<LoginResponse> {
  const res = await apiClient.post('/api/v1/auth/login', data);
  return res.data;
}

/** 登出：后端 no-op，前端清 token */
export async function logoutUser(): Promise<void> {
  await apiClient.post('/api/v1/auth/logout');
  clearToken();
}

/** 获取当前登录用户信息 */
export async function getCurrentUser(): Promise<AuthUser> {
  const res = await apiClient.get('/api/v1/auth/me');
  return res.data;
}

/** 修改密码 */
export async function changePassword(data: ChangePasswordRequest): Promise<void> {
  await apiClient.post('/api/v1/auth/change-password', data);
}

// ---------- React Query Hooks ----------

/**
 * 获取当前用户（/me）。
 * enabled 条件：有 token 才查询，避免未登录时发无意义请求。
 */
export function useMe() {
  const hasToken = !!getToken();
  return useQuery<AuthUser>({
    queryKey: ['me'],
    queryFn: getCurrentUser,
    enabled: hasToken,
    retry: false, // 401 不重试（拦截器会跳转 /login）
  });
}

/** 登录 mutation：成功后存 token + invalidate /me */
export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: loginUser,
    onSuccess: (data) => {
      setToken(data.access_token);
      // 刷新 /me 缓存
      queryClient.invalidateQueries({ queryKey: ['me'] });
    },
  });
}

/** 注册 mutation */
export function useRegister() {
  return useMutation({
    mutationFn: registerUser,
  });
}

/** 登出 mutation：清 token + 清所有缓存 */
export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: logoutUser,
    onSettled: () => {
      // 无论后端登出是否成功，都清前端状态
      clearToken();
      queryClient.clear();
    },
  });
}

/** 修改密码 mutation */
export function useChangePassword() {
  return useMutation({
    mutationFn: changePassword,
  });
}
