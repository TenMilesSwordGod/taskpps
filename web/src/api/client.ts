import axios from 'axios';

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

// 响应拦截器：将后端返回的 detail 信息注入到错误消息中
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error?.response?.data?.detail;
    if (typeof detail === 'string' && detail.length > 0) {
      error.message = detail;
    }
    return Promise.reject(error);
  },
);

export default apiClient;
