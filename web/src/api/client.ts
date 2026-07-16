import axios from 'axios';

/**
 * Token 管理：localStorage 持久化（key=taskpps_token）。
 * 设计决策：用 localStorage 而非 sessionStorage，让 token 在标签页间共享、
 * 关闭浏览器后仍保留（24h 有效期内免重复登录）。
 */
export const TOKEN_KEY = 'taskpps_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * 开发环境下走 Vite proxy（/api → localhost:26521），
 * 生产环境下 baseURL 由环境变量指定或同源访问。
 */
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 通过 VITE_API_KEY 环境变量注入 API Key 认证
const apiKey = import.meta.env.VITE_API_KEY as string | undefined;
if (apiKey) {
  apiClient.defaults.headers.common['X-API-Key'] = apiKey;
}

// 请求拦截器：自动附加 Authorization: Bearer <token>
// 从 localStorage 读 token，有则附加到请求头
apiClient.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// 响应拦截器：将后端返回的 detail 信息注入到错误消息中 + 401 处理
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error?.response?.data?.detail;
    if (typeof detail === 'string' && detail.length > 0) {
      error.message = detail;
    }

    // 401 处理：清 token + 跳转 /login（避免登录页请求本身触发死循环）
    const status = error?.response?.status;
    const url = error?.config?.url || '';
    if (status === 401 && !url.includes('/api/v1/auth/login')) {
      clearToken();
      // 避免在 /login 页面重复跳转
      const currentPath = window.location.pathname;
      if (currentPath !== '/login') {
        const redirect = encodeURIComponent(currentPath);
        window.location.href = `/login?redirect=${redirect}`;
      }
    }

    return Promise.reject(error);
  },
);

export default apiClient;
